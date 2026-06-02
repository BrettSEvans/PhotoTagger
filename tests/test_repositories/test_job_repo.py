"""Tests for JobRepository (independent of Flask)."""

import pytest
import sqlite3
import tempfile
from pathlib import Path

from src.repositories.job import JobRepository
from src.schema import init_schema


@pytest.fixture
def conn_and_repo():
    """Create an in-memory database and JobRepository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_schema(conn)

        import threading
        lock = threading.RLock()
        repo = JobRepository(conn, lock)
        yield repo, conn
        conn.close()


def test_create_processing_job(conn_and_repo):
    """Test creating a processing job."""
    repo, conn = conn_and_repo

    job_id = repo.create_processing_job("ocr", {"photo_id": 1})

    assert job_id > 0
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM processing_jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    assert row is not None
    assert row["type"] == "ocr"
    assert row["status"] == "queued"


def test_get_processing_job(conn_and_repo):
    """Test retrieving a processing job."""
    repo, conn = conn_and_repo

    job_id = repo.create_processing_job("detection", {"photo_ids": [1, 2, 3]})
    job = repo.get_processing_job(job_id)

    assert job is not None
    assert job["id"] == job_id
    assert job["type"] == "detection"


def test_update_processing_job(conn_and_repo):
    """Test updating a processing job."""
    repo, conn = conn_and_repo

    job_id = repo.create_processing_job("test", {})
    repo.update_processing_job(job_id, status="running", progress=50)

    job = repo.get_processing_job(job_id)
    assert job["status"] == "running"
    assert job["progress"] == 50
