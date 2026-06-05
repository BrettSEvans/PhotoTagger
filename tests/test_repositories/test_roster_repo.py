"""Tests for RosterRepository (independent of Flask)."""

import pytest
import sqlite3
import tempfile
from pathlib import Path

from src.repositories.roster import RosterRepository
from src.schema import init_schema


@pytest.fixture
def conn_and_repo():
    """Create an in-memory database and RosterRepository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_schema(conn)

        import threading
        lock = threading.RLock()
        repo = RosterRepository(conn, lock)
        yield repo, conn
        conn.close()


def test_add_roster_entry(conn_and_repo):
    """Test adding a roster entry."""
    repo, conn = conn_and_repo

    repo.add_roster_entry(
        team_name="Team A",
        team_year=2024,
        jersey_number="23",
        player_name="Alice Smith"
    )

    cursor = conn.cursor()
    cursor.execute(
        "SELECT player_name FROM rosters WHERE team_name = ? AND team_year = ? AND jersey_number = ?",
        ("Team A", 2024, "23")
    )
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "Alice Smith"


def test_roster_entry_exists(conn_and_repo):
    """Test checking if roster entry exists."""
    repo, _ = conn_and_repo

    assert not repo.roster_entry_exists("Team A", 2024, "23")

    repo.add_roster_entry("Team A", 2024, "23", "Alice Smith")

    assert repo.roster_entry_exists("Team A", 2024, "23")


def test_import_roster_entries(conn_and_repo):
    """Test importing multiple roster entries."""
    repo, _ = conn_and_repo

    rows = [
        {"jersey_number": "23", "player_name": "Alice"},
        {"jersey_number": "42", "player_name": "Bob"},
        {"jersey_number": "7", "player_name": "Charlie"},
    ]

    result = repo.import_roster_entries("Team A", 2024, rows)

    assert result["imported"] == 3
    assert result["skipped"] == 0
    assert result["failed"] == 0
    assert result["success"] is True


def test_import_roster_entries_with_duplicates_skip(conn_and_repo):
    """Test import with duplicate skip policy."""
    repo, _ = conn_and_repo

    repo.add_roster_entry("Team A", 2024, "23", "Alice")

    rows = [
        {"jersey_number": "23", "player_name": "Alice Updated"},
        {"jersey_number": "42", "player_name": "Bob"},
    ]

    result = repo.import_roster_entries("Team A", 2024, rows, duplicate_policy="skip")

    assert result["imported"] == 1
    assert result["skipped"] == 1


def test_import_roster_entries_with_duplicates_replace(conn_and_repo):
    """Test import with duplicate replace policy."""
    repo, _ = conn_and_repo

    repo.add_roster_entry("Team A", 2024, "23", "Alice")

    rows = [
        {"jersey_number": "23", "player_name": "Alice Updated"},
        {"jersey_number": "42", "player_name": "Bob"},
    ]

    result = repo.import_roster_entries("Team A", 2024, rows, duplicate_policy="replace")

    assert result["imported"] == 2
    assert result["skipped"] == 0


def test_get_player_name(conn_and_repo):
    """Test looking up player name by jersey."""
    repo, _ = conn_and_repo

    repo.add_roster_entry("Team A", 2024, "23", "Alice Smith")

    name = repo.get_player_name("Team A", 2024, "23")
    assert name == "Alice Smith"

    missing = repo.get_player_name("Team A", 2024, "99")
    assert missing is None


def test_get_all_roster_entries(conn_and_repo):
    """Test retrieving all roster entries."""
    repo, _ = conn_and_repo

    repo.add_roster_entry("Team A", 2024, "23", "Alice", uniform_color="red")
    repo.add_roster_entry("Team A", 2024, "42", "Bob", uniform_color="red")
    repo.add_roster_entry("Team B", 2024, "5", "Charlie", uniform_color="blue")

    entries = repo.get_all_roster_entries()

    assert len(entries) == 3
    # Should be ordered by team then jersey
    assert entries[0]["team_name"] == "Team A"
    assert entries[2]["team_name"] == "Team B"


def test_delete_roster_entry(conn_and_repo):
    """Test deleting a roster entry."""
    repo, conn = conn_and_repo

    repo.add_roster_entry("Team A", 2024, "23", "Alice")

    cursor = conn.cursor()
    cursor.execute("SELECT id FROM rosters WHERE player_name = ?", ("Alice",))
    entry_id = cursor.fetchone()[0]

    repo.delete_roster_entry(entry_id)

    cursor.execute("SELECT COUNT(*) FROM rosters WHERE id = ?", (entry_id,))
    assert cursor.fetchone()[0] == 0


def test_update_roster_entry(conn_and_repo):
    """Test updating a roster entry."""
    repo, conn = conn_and_repo

    repo.add_roster_entry("Team A", 2024, "23", "Alice")

    cursor = conn.cursor()
    cursor.execute("SELECT id FROM rosters WHERE player_name = ?", ("Alice",))
    entry_id = cursor.fetchone()[0]

    updated = repo.update_roster_entry(entry_id, player_name="Alice Updated")

    assert updated["player_name"] == "Alice Updated"
    # jersey_number is stored as INTEGER in the DB; update returns it as int.
    assert str(updated["jersey_number"]) == "23"


def test_update_roster_entry_nonexistent(conn_and_repo):
    """Test updating nonexistent entry raises error."""
    repo, _ = conn_and_repo

    with pytest.raises(ValueError, match="not found"):
        repo.update_roster_entry(999, player_name="Nobody")


def test_search_roster(conn_and_repo):
    """Test searching roster by player name or jersey."""
    repo, _ = conn_and_repo

    repo.add_roster_entry("Team A", 2024, "23", "Alice Smith")
    repo.add_roster_entry("Team A", 2024, "42", "Bob Jones")
    repo.add_roster_entry("Team A", 2024, "5", "Charlie Brown")

    # Search by name
    results = repo.search_roster("Alice")
    assert len(results) == 1
    assert results[0]["player_name"] == "Alice Smith"

    # Search by jersey
    results = repo.search_roster("42")
    assert len(results) == 1
    assert results[0]["player_name"] == "Bob Jones"

    # Partial search
    results = repo.search_roster("l")
    assert len(results) >= 2  # Alice and Charlie both contain 'l'


def test_get_roster_entry_by_id(conn_and_repo):
    """Test retrieving a roster entry by ID."""
    repo, conn = conn_and_repo

    repo.add_roster_entry("Team A", 2024, "23", "Alice", uniform_color="red")

    cursor = conn.cursor()
    cursor.execute("SELECT id FROM rosters WHERE player_name = ?", ("Alice",))
    entry_id = cursor.fetchone()[0]

    entry = repo.get_roster_entry_by_id(entry_id)

    assert entry is not None
    assert entry["player_name"] == "Alice"
    assert entry["uniform_color"] == "red"

    missing = repo.get_roster_entry_by_id(999)
    assert missing is None


# ---------------------------------------------------------------------------
# find_by_jersey_color_and_team (lines 358-373)
# ---------------------------------------------------------------------------

def test_find_by_jersey_color_and_team_found(conn_and_repo):
    repo, _ = conn_and_repo
    repo.add_roster_entry("Team A", 2024, "23", "Alice", uniform_color="red")
    result = repo.find_by_jersey_color_and_team(23, "Team A", "red", 2024)
    assert result is not None
    assert result["player_name"] == "Alice"


def test_find_by_jersey_color_and_team_not_found(conn_and_repo):
    repo, _ = conn_and_repo
    result = repo.find_by_jersey_color_and_team(99, "Team A", "red", 2024)
    assert result is None


def test_find_by_jersey_color_wrong_color(conn_and_repo):
    repo, _ = conn_and_repo
    repo.add_roster_entry("Team A", 2024, "23", "Alice", uniform_color="red")
    result = repo.find_by_jersey_color_and_team(23, "Team A", "blue", 2024)
    assert result is None


# ---------------------------------------------------------------------------
# _color_match_score (lines 386, 405)
# ---------------------------------------------------------------------------

def test_color_match_score_none_input(conn_and_repo):
    from src.repositories.roster import RosterRepository
    # None detected → return 0.0 (line 386)
    score = RosterRepository._color_match_score(None, "red")
    assert score == 0.0


def test_color_match_score_family_match(conn_and_repo):
    from src.repositories.roster import RosterRepository
    # "crimson" is in the red family → 0.9 (line 405)
    score = RosterRepository._color_match_score("crimson", "dark red")
    assert score == 0.9


def test_color_match_score_exact(conn_and_repo):
    from src.repositories.roster import RosterRepository
    score = RosterRepository._color_match_score("red", "red")
    assert score == 1.0


# ---------------------------------------------------------------------------
# import_roster_entries error paths (lines 67-70, 73-75, 84-86)
# ---------------------------------------------------------------------------

def test_import_invalid_jersey_number_increments_failed(conn_and_repo):
    repo, _ = conn_and_repo
    rows = [{"jersey_number": "not_a_number", "player_name": "Alice"}]
    result = repo.import_roster_entries("Team A", 2024, rows)
    assert result["failed"] == 1
    assert result["imported"] == 0


def test_import_missing_player_name_increments_failed(conn_and_repo):
    repo, _ = conn_and_repo
    rows = [{"jersey_number": "7", "player_name": ""}]
    result = repo.import_roster_entries("Team A", 2024, rows)
    assert result["failed"] == 1


# ---------------------------------------------------------------------------
# update_roster_entry error paths (lines 190-191, 203, 219)
# ---------------------------------------------------------------------------

def test_update_roster_invalid_jersey_raises(conn_and_repo):
    repo, conn = conn_and_repo
    repo.add_roster_entry("Team A", 2024, "23", "Alice")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM rosters WHERE player_name = ?", ("Alice",))
    entry_id = cursor.fetchone()[0]
    with pytest.raises(ValueError):
        repo.update_roster_entry(entry_id, jersey_number="notanint")


def test_update_roster_empty_player_name_raises(conn_and_repo):
    repo, conn = conn_and_repo
    repo.add_roster_entry("Team A", 2024, "23", "Alice")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM rosters WHERE player_name = ?", ("Alice",))
    entry_id = cursor.fetchone()[0]
    with pytest.raises(ValueError, match="player_name"):
        repo.update_roster_entry(entry_id, player_name="")


def test_update_roster_duplicate_jersey_raises(conn_and_repo):
    repo, conn = conn_and_repo
    repo.add_roster_entry("Team A", 2024, "7", "Alice")
    repo.add_roster_entry("Team A", 2024, "15", "Bob")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM rosters WHERE player_name = ?", ("Alice",))
    alice_id = cursor.fetchone()[0]
    # Try to change Alice to jersey 15 (Bob's jersey) → unique constraint
    with pytest.raises(ValueError):
        repo.update_roster_entry(alice_id, jersey_number=15)
