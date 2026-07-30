"""Guards the invariant that the shared SQLite connection is never used unlocked.

``Database`` opens a single ``sqlite3`` connection with ``check_same_thread=False``
and shares it across every repository. That disables Python's own thread guard, so
the ``Database._lock`` mutex is the *only* thing serializing access. Flask runs with
``threaded=True``, so any method that touches the connection without holding the lock
can execute concurrently with another thread's statement on the same connection.

That is not a benign race: two threads inside ``sqlite3_prepare`` on one connection
corrupt SQLite's per-connection heap, which shows up as "database is locked", then
"disk I/O error", a write transaction wedged open, and ultimately a SIGSEGV inside
libsqlite3. It broke roster import — every row failed while the dashboard polled.
"""

import ast
import threading
from pathlib import Path

import pytest

from src.db import Database

SRC = Path(__file__).resolve().parent.parent / "src"

# Lifecycle methods that run before any worker thread exists, so the lock is moot.
_SINGLE_THREADED_LIFECYCLE = {"__init__", "init_schema", "close"}

# src/cli.py is a standalone single-threaded entrypoint that builds its own Database
# and exits; it is never served concurrently, so the locking invariant does not apply.
_NOT_SERVED_CONCURRENTLY = {"cli.py"}


def _connection_users_without_lock(path: Path):
    """Yield ``(lineno, name)`` for methods touching the connection outside the lock."""
    tree = ast.parse(path.read_text())
    for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        if fn.name in _SINGLE_THREADED_LIFECYCLE:
            continue
        touches_conn = any(
            isinstance(n, ast.Attribute) and n.attr in ("_conn", "conn")
            for n in ast.walk(fn)
        )
        if not touches_conn:
            continue
        holds_lock = any(
            isinstance(n, ast.With)
            and any(
                isinstance(i.context_expr, ast.Attribute)
                and i.context_expr.attr in ("_lock", "lock")
                for i in n.items
            )
            for n in ast.walk(fn)
        )
        if not holds_lock:
            yield fn.lineno, fn.name


def test_every_connection_user_holds_the_shared_lock():
    """No repository method may touch the shared connection without the lock."""
    offenders = [
        f"{path.relative_to(SRC.parent)}:{lineno} {name}()"
        for path in sorted(SRC.rglob("*.py"))
        if path.name not in _NOT_SERVED_CONCURRENTLY
        for lineno, name in _connection_users_without_lock(path)
    ]
    assert not offenders, (
        "These methods use the shared SQLite connection without holding "
        "Database._lock, which corrupts the connection under concurrent access:\n  "
        + "\n  ".join(offenders)
    )


def test_concurrent_reads_during_import_do_not_corrupt_the_connection(tmp_path):
    """Polling the review path while importing must not break the import.

    This mirrors production: the dashboard polls review endpoints (which call
    ``resolve_roster_candidates``) while a roster import writes rows.
    """
    db = Database(str(tmp_path / "concurrent.db"))
    db.init_schema()

    context = [{"team_name": "Test Team", "team_year": 2026, "uniform_color": None}]
    db.roster.add_roster_entry("Test Team", 2026, 10, "Existing Player")

    stop = threading.Event()
    reader_errors: list[str] = []

    def poll_review_path():
        while not stop.is_set():
            try:
                db.roster.resolve_roster_candidates("10", None, context)
            except Exception as exc:  # pragma: no cover - only on regression
                reader_errors.append(repr(exc))

    readers = [threading.Thread(target=poll_review_path, daemon=True) for _ in range(8)]
    for t in readers:
        t.start()
    try:
        rows = [
            {"jersey_number": str(n), "player_name": f"Player {n}"}
            for n in range(20, 60)
        ]
        result = db.roster.import_roster_entries("Test Team", 2026, rows, "replace")
    finally:
        stop.set()
        for t in readers:
            t.join(timeout=5)

    assert reader_errors == [], f"concurrent reads failed: {reader_errors[:3]}"
    assert result["failed"] == 0, f"import failed under load: {result['errors'][:3]}"
    assert result["imported"] == len(rows)
    db.close()
