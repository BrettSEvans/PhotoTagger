import os
import pytest
from src.db import Database

@pytest.fixture
def test_db():
    """Create an in-memory SQLite database for testing."""
    db = Database(":memory:")
    db.init_schema()
    yield db
    db.close()

def test_database_initialization(test_db):
    """Verify schema exists after init."""
    cursor = test_db.conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    assert "photos" in tables
    assert "ocr_results" in tables

def test_add_photo(test_db, tmp_path):
    """Test adding a photo to the database."""
    # Create a dummy photo file
    photo_file = tmp_path / "test.jpg"
    photo_file.write_bytes(b"fake jpg data")

    photo_id = test_db.photos.add_photo(str(photo_file))
    assert photo_id is not None
    assert photo_id > 0

    # Verify it was stored
    photos = test_db.photos.get_all_photos()
    assert len(photos) == 1
    assert photos[0]["file_path"] == str(photo_file)

def test_photo_exists(test_db, tmp_path):
    """Test checking if a photo already exists."""
    photo_file = tmp_path / "test.jpg"
    photo_file.write_bytes(b"fake jpg data")

    file_hash = Database._compute_file_hash(str(photo_file))

    # Should not exist yet
    assert not test_db.photos.photo_exists(file_hash)

    # Add it
    test_db.photos.add_photo(str(photo_file), file_hash)

    # Should exist now
    assert test_db.photos.photo_exists(file_hash)

def test_add_ocr_result(test_db, tmp_path):
    """Test adding OCR results for a photo."""
    photo_file = tmp_path / "test.jpg"
    photo_file.write_bytes(b"fake jpg data")

    photo_id = test_db.photos.add_photo(str(photo_file))
    test_db.photos.add_ocr_result(photo_id, "23", 0.95, "23 in white text")

    result = test_db.photos.get_photo_ocr(photo_id)
    assert result["jersey_number"] == "23"
    assert result["confidence"] == 0.95

def test_get_photo_by_jersey(test_db, tmp_path):
    """Test searching photos by jersey number."""
    # Create two dummy photos
    photo1 = tmp_path / "photo1.jpg"
    photo2 = tmp_path / "photo2.jpg"
    photo1.write_bytes(b"fake jpg 1")
    photo2.write_bytes(b"fake jpg 2")

    # Add both
    id1 = test_db.photos.add_photo(str(photo1))
    id2 = test_db.photos.add_photo(str(photo2))

    # Add OCR results: both have jersey 23
    test_db.photos.add_ocr_result(id1, "23", 0.95, "23")
    test_db.photos.add_ocr_result(id2, "23", 0.88, "23")

    # Search for jersey 23
    results = test_db.photos.get_photo_by_jersey("23")
    assert len(results) == 2
    assert results[0]["file_path"] == str(photo1)  # Higher confidence first

def test_duplicate_detection(test_db, tmp_path):
    """Test that duplicate photos are properly detected."""
    # Create one photo file
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"identical data")

    file_hash = Database._compute_file_hash(str(photo))

    # Add it once
    photo_id = test_db.photos.add_photo(str(photo), file_hash)
    assert photo_id is not None

    # Try to add again - should raise error due to UNIQUE constraint
    with pytest.raises(Exception):
        test_db.photos.add_photo(str(photo), file_hash)
