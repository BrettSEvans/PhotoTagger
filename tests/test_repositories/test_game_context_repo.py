"""Tests for GameContextRepository (independent of Flask)."""

import pytest
import sqlite3
import tempfile
from pathlib import Path

from src.repositories.game_context import GameContextRepository
from src.schema import init_schema


@pytest.fixture
def conn_and_repo():
    """Create an in-memory database and GameContextRepository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_schema(conn)

        import threading
        lock = threading.RLock()
        repo = GameContextRepository(conn, lock)
        yield repo, conn
        conn.close()


def test_set_and_get_game_context(conn_and_repo):
    """Test setting and retrieving game context."""
    repo, conn = conn_and_repo

    teams = [
        {"team_name": "Team A", "team_year": 2024, "uniform_color": "red", "position": 0},
        {"team_name": "Team B", "team_year": 2024, "uniform_color": "blue", "position": 1},
    ]
    repo.set_game_context(teams)

    retrieved = repo.get_game_context()
    assert len(retrieved) == 2
    assert retrieved[0]["team_name"] == "Team A"
    assert retrieved[0]["uniform_color"] == "red"
    assert retrieved[1]["team_name"] == "Team B"


def test_set_game_context_replaces_existing(conn_and_repo):
    """Test that set_game_context clears old data."""
    repo, conn = conn_and_repo

    # Set initial context
    teams1 = [
        {"team_name": "Old Team", "team_year": 2023, "uniform_color": "green", "position": 0},
    ]
    repo.set_game_context(teams1)

    # Replace with new context
    teams2 = [
        {"team_name": "New Team", "team_year": 2024, "uniform_color": "yellow", "position": 0},
    ]
    repo.set_game_context(teams2)

    retrieved = repo.get_game_context()
    assert len(retrieved) == 1
    assert retrieved[0]["team_name"] == "New Team"


def test_get_game_context_empty(conn_and_repo):
    """Test getting game context when none is set."""
    repo, conn = conn_and_repo

    retrieved = repo.get_game_context()
    assert retrieved == []
