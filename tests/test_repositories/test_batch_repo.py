"""Tests for BatchRepository (independent of Flask)."""

import pytest
import sqlite3
import tempfile
from pathlib import Path

from src.repositories.batch import BatchRepository
from src.schema import init_schema


@pytest.fixture
def conn_and_repo():
    """Create an in-memory database and BatchRepository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_schema(conn)

        import threading
        lock = threading.RLock()
        repo = BatchRepository(conn, lock)
        yield repo, conn
        conn.close()


def test_create_batch(conn_and_repo):
    """Test creating a batch."""
    repo, conn = conn_and_repo

    batch_id = repo.create_batch("/path/to/photos", name="Tournament 2024")

    assert batch_id > 0
    batch = repo.get_batch(batch_id)
    assert batch is not None
    assert batch["name"] == "Tournament 2024"
    assert batch["source_folder"] == "/path/to/photos"


def test_create_batch_idempotent(conn_and_repo):
    """Test that creating batch for same folder returns existing ID."""
    repo, conn = conn_and_repo

    id1 = repo.create_batch("/photos/event1", name="Event 1")
    id2 = repo.create_batch("/photos/event1", name="Event 1 Updated")

    assert id1 == id2


def test_get_all_batches(conn_and_repo):
    """Test retrieving all batches."""
    repo, conn = conn_and_repo

    repo.create_batch("/photos/batch1", name="Batch 1")
    repo.create_batch("/photos/batch2", name="Batch 2")

    batches = repo.get_all_batches()
    assert len(batches) == 2


def test_update_batch(conn_and_repo):
    """Test updating batch metadata."""
    repo, conn = conn_and_repo

    batch_id = repo.create_batch("/photos/test")
    repo.update_batch(batch_id, team_name="Team A", team_year=2024)

    batch = repo.get_batch(batch_id)
    assert batch["team_name"] == "Team A"
    assert batch["team_year"] == 2024


def test_delete_batch(conn_and_repo):
    """Test deleting a batch."""
    repo, conn = conn_and_repo

    batch_id = repo.create_batch("/photos/delete_test")
    deleted_count = repo.delete_batch(batch_id)

    assert deleted_count == 0  # No photos in batch
    batch = repo.get_batch(batch_id)
    assert batch is None


def test_get_batch_by_source_folder(conn_and_repo):
    """Test retrieving batch by source folder."""
    repo, conn = conn_and_repo

    batch_id = repo.create_batch("/photos/tournament", name="Tournament")
    batch = repo.get_batch_by_source_folder("/photos/tournament")

    assert batch is not None
    assert batch["id"] == batch_id


def test_get_photos_by_batch_empty(conn_and_repo):
    """Test getting photos for empty batch."""
    repo, conn = conn_and_repo

    batch_id = repo.create_batch("/photos/empty")
    photos = repo.get_photos_by_batch(batch_id)

    assert photos == []


def test_update_batch_photo_count(conn_and_repo):
    """Test updating photo count for batch."""
    repo, conn = conn_and_repo

    batch_id = repo.create_batch("/photos/count_test")
    count = repo.update_batch_photo_count(batch_id)

    assert count == 0
