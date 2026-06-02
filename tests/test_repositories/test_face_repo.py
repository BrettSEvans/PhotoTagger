"""Tests for FaceRepository (independent of Flask)."""

import pytest
import sqlite3
import tempfile
import json
from pathlib import Path

from src.repositories.face import FaceRepository
from src.schema import init_schema


@pytest.fixture
def conn_and_repo():
    """Create an in-memory database and FaceRepository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_schema(conn)

        import threading
        lock = threading.RLock()
        repo = FaceRepository(conn, lock)
        yield repo, conn
        conn.close()


def test_add_face(conn_and_repo):
    """Test adding a face."""
    repo, conn = conn_and_repo

    embedding = [0.1] * 384
    bbox = [10, 20, 100, 150]
    face_id = repo.add_face(photo_id=1, embedding=embedding, bbox=bbox, confidence=0.95)

    assert face_id > 0


def test_get_faces_by_photo(conn_and_repo):
    """Test retrieving faces for a photo."""
    repo, conn = conn_and_repo

    embedding = [0.1] * 384
    bbox = [10, 20, 100, 150]
    repo.add_face(photo_id=1, embedding=embedding, bbox=bbox, confidence=0.95)
    repo.add_face(photo_id=1, embedding=embedding, bbox=[200, 200, 300, 300], confidence=0.85)

    faces = repo.get_faces_by_photo(photo_id=1)
    assert len(faces) == 2
    assert faces[0]["confidence"] == 0.95


def test_get_all_faces(conn_and_repo):
    """Test retrieving all faces."""
    repo, conn = conn_and_repo

    embedding = [0.1] * 384
    bbox = [10, 20, 100, 150]
    repo.add_face(photo_id=1, embedding=embedding, bbox=bbox, confidence=0.95)
    repo.add_face(photo_id=2, embedding=embedding, bbox=bbox, confidence=0.85)

    faces = repo.get_all_faces()
    assert len(faces) == 2


def test_get_face_by_id(conn_and_repo):
    """Test retrieving a single face."""
    repo, conn = conn_and_repo

    embedding = [0.1] * 384
    bbox = [10, 20, 100, 150]
    face_id = repo.add_face(photo_id=1, embedding=embedding, bbox=bbox, confidence=0.95)

    face = repo.get_face_by_id(face_id)
    assert face is not None
    assert face["photo_id"] == 1
    assert face["confidence"] == 0.95


def test_get_face_count(conn_and_repo):
    """Test counting faces."""
    repo, conn = conn_and_repo

    embedding = [0.1] * 384
    bbox = [10, 20, 100, 150]
    repo.add_face(photo_id=1, embedding=embedding, bbox=bbox, confidence=0.95)
    repo.add_face(photo_id=2, embedding=embedding, bbox=bbox, confidence=0.85)

    count = repo.get_face_count()
    assert count == 2


def test_photo_has_faces(conn_and_repo):
    """Test checking if photo has faces."""
    repo, conn = conn_and_repo

    embedding = [0.1] * 384
    bbox = [10, 20, 100, 150]

    assert not repo.photo_has_faces(photo_id=1)
    repo.add_face(photo_id=1, embedding=embedding, bbox=bbox, confidence=0.95)
    assert repo.photo_has_faces(photo_id=1)


def test_get_face_photo_location(conn_and_repo):
    """Test getting face location in photo."""
    repo, conn = conn_and_repo

    embedding = [0.1] * 384
    bbox = [10, 20, 100, 150]
    face_id = repo.add_face(photo_id=1, embedding=embedding, bbox=bbox, confidence=0.95)

    location = repo.get_face_photo_location(face_id)
    assert location is not None
    assert location["photo_id"] == 1
    assert location["face_bbox"] == bbox


def test_deassign_faces(conn_and_repo):
    """Test deassigning faces from cluster."""
    repo, conn = conn_and_repo

    embedding = [0.1] * 384
    bbox = [10, 20, 100, 150]
    face_id = repo.add_face(photo_id=1, embedding=embedding, bbox=bbox, confidence=0.95)

    # Manually set cluster_id to simulate assignment
    cursor = conn.cursor()
    cursor.execute("UPDATE faces SET cluster_id = ? WHERE id = ?", (1, face_id))
    conn.commit()

    result = repo.deassign_faces([face_id])
    assert result["deassigned"] == 1

    face = repo.get_face_by_id(face_id)
    assert face["cluster_id"] is None
