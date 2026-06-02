"""Tests for PhotoRepository (independent of Flask)."""

import pytest
import sqlite3
import tempfile
from pathlib import Path

from src.repositories.photo import PhotoRepository
from src.schema import init_schema


@pytest.fixture
def temp_photo(tmp_path):
    """Create a temporary test photo file."""
    photo_file = tmp_path / "test.jpg"
    photo_file.write_bytes(b"fake jpeg content")
    return str(photo_file)


@pytest.fixture
def conn_and_repo():
    """Create an in-memory database and PhotoRepository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_schema(conn)

        import threading
        lock = threading.RLock()
        repo = PhotoRepository(conn, lock)
        yield repo, conn
        conn.close()


def test_add_photo(conn_and_repo, temp_photo):
    """Test adding a photo."""
    repo, conn = conn_and_repo

    photo_id = repo.add_photo(file_path=temp_photo, source_folder="/photos")

    assert photo_id > 0

    cursor = conn.cursor()
    cursor.execute("SELECT file_path, source_folder FROM photos WHERE id = ?", (photo_id,))
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == temp_photo


def test_photo_exists(conn_and_repo, temp_photo):
    """Test checking if photo exists."""
    repo, _ = conn_and_repo

    photo_id = repo.add_photo(file_path=temp_photo)

    cursor = repo._conn.cursor()
    cursor.execute("SELECT file_hash FROM photos WHERE id = ?", (photo_id,))
    file_hash = cursor.fetchone()[0]

    assert repo.photo_exists(file_hash)
    assert not repo.photo_exists("nonexistent_hash")


def test_count_photos(conn_and_repo, tmp_path):
    """Test counting photos."""
    repo, _ = conn_and_repo

    assert repo.count_photos() == 0

    # Create two different temp files
    photo1 = tmp_path / "photo1.jpg"
    photo1.write_bytes(b"fake jpeg 1")
    photo2 = tmp_path / "photo2.jpg"
    photo2.write_bytes(b"fake jpeg 2")

    repo.add_photo(file_path=str(photo1))
    repo.add_photo(file_path=str(photo2))

    assert repo.count_photos() == 2


def test_get_all_photos(conn_and_repo, tmp_path):
    """Test retrieving all photos."""
    repo, _ = conn_and_repo

    photo1 = tmp_path / "photo1.jpg"
    photo1.write_bytes(b"fake jpeg 1")
    photo2 = tmp_path / "photo2.jpg"
    photo2.write_bytes(b"fake jpeg 2")

    repo.add_photo(file_path=str(photo1), source_folder="/photos1")
    repo.add_photo(file_path=str(photo2), source_folder="/photos2")

    photos = repo.get_all_photos()

    assert len(photos) == 2


def test_get_all_photos_with_limit(conn_and_repo, tmp_path):
    """Test pagination of photos."""
    repo, _ = conn_and_repo

    for i in range(5):
        photo = tmp_path / f"photo{i}.jpg"
        photo.write_bytes(f"fake jpeg {i}".encode())
        repo.add_photo(file_path=str(photo))

    photos = repo.get_all_photos(limit=2, offset=0)
    assert len(photos) == 2

    photos = repo.get_all_photos(limit=2, offset=2)
    assert len(photos) == 2


def test_get_photo_by_id(conn_and_repo, temp_photo):
    """Test retrieving a photo by ID."""
    repo, _ = conn_and_repo

    photo_id = repo.add_photo(file_path=temp_photo)

    photo = repo.get_photo_by_id(photo_id)
    assert photo is not None
    assert photo["id"] == photo_id

    missing = repo.get_photo_by_id(999)
    assert missing is None


def test_add_ocr_result(conn_and_repo, temp_photo):
    """Test adding OCR results."""
    repo, conn = conn_and_repo

    photo_id = repo.add_photo(file_path=temp_photo)

    repo.add_ocr_result(
        photo_id=photo_id,
        jersey_number="23",
        confidence=0.95,
        raw_text="23",
        uniform_color="red"
    )

    cursor = conn.cursor()
    cursor.execute("SELECT jersey_number, confidence FROM ocr_results WHERE photo_id = ?", (photo_id,))
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "23"
    assert row[1] == 0.95


def test_get_photo_ocr(conn_and_repo, temp_photo):
    """Test retrieving OCR for a photo."""
    repo, _ = conn_and_repo

    photo_id = repo.add_photo(file_path=temp_photo)

    repo.add_ocr_result(photo_id=photo_id, jersey_number="23", confidence=0.95, raw_text="23")

    ocr = repo.get_photo_ocr(photo_id)
    assert ocr is not None
    assert ocr["jersey_number"] == "23"

    missing_ocr = repo.get_photo_ocr(999)
    assert missing_ocr is None


def test_get_photo_by_jersey(conn_and_repo, tmp_path):
    """Test finding photos by jersey number."""
    repo, _ = conn_and_repo

    photo1 = tmp_path / "photo1.jpg"
    photo1.write_bytes(b"fake jpeg 1")
    photo2 = tmp_path / "photo2.jpg"
    photo2.write_bytes(b"fake jpeg 2")

    photo_id1 = repo.add_photo(file_path=str(photo1))
    photo_id2 = repo.add_photo(file_path=str(photo2))

    repo.add_ocr_result(photo_id=photo_id1, jersey_number="23", confidence=0.95, raw_text="23")
    repo.add_ocr_result(photo_id=photo_id2, jersey_number="42", confidence=0.90, raw_text="42")

    photos = repo.get_photo_by_jersey("23")
    assert len(photos) == 1
    assert photos[0]["jersey_number"] == "23"


def test_get_latest_ocr_by_photo_ids(conn_and_repo, tmp_path):
    """Test retrieving latest OCR for multiple photos."""
    repo, _ = conn_and_repo

    photo1 = tmp_path / "photo1.jpg"
    photo1.write_bytes(b"fake jpeg 1")
    photo2 = tmp_path / "photo2.jpg"
    photo2.write_bytes(b"fake jpeg 2")

    photo_id1 = repo.add_photo(file_path=str(photo1))
    photo_id2 = repo.add_photo(file_path=str(photo2))

    repo.add_ocr_result(photo_id=photo_id1, jersey_number="23", confidence=0.95, raw_text="23")
    repo.add_ocr_result(photo_id=photo_id2, jersey_number="42", confidence=0.90, raw_text="42")

    ocr_map = repo.get_latest_ocr_by_photo_ids([photo_id1, photo_id2])

    assert photo_id1 in ocr_map
    assert photo_id2 in ocr_map
    assert ocr_map[photo_id1]["jersey_number"] == "23"
    assert ocr_map[photo_id2]["jersey_number"] == "42"


def test_get_assigned_player_for_photo(conn_and_repo, temp_photo):
    """Test getting assigned player for a photo."""
    repo, conn = conn_and_repo

    photo_id = repo.add_photo(file_path=temp_photo)

    # Without assignment, should return None
    assert repo.get_assigned_player_for_photo(photo_id) is None

    # With assignment (via cluster), should return player name
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO player_clusters (player_name, jersey_number)
        VALUES (?, ?)
    """, ("Alice", "23"))
    cluster_id = cursor.lastrowid

    embedding = [0.1] * 384
    cursor.execute("""
        INSERT INTO faces (photo_id, embedding, bbox_x0, bbox_y0, bbox_x1, bbox_y1, confidence, cluster_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (photo_id, __import__('json').dumps(embedding), 10, 20, 100, 150, 0.95, cluster_id))
    conn.commit()

    player = repo.get_assigned_player_for_photo(photo_id)
    assert player == "Alice"
