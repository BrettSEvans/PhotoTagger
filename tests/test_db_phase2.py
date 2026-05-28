import pytest
from src.db import Database

@pytest.fixture
def test_db():
    db = Database(":memory:")
    db.init_schema()
    yield db
    db.close()

def test_faces_table_exists(test_db):
    """Verify faces table created."""
    cursor = test_db.conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='faces'")
    assert cursor.fetchone() is not None

def test_add_face(test_db, tmp_path):
    """Test adding a face record."""
    photo_file = tmp_path / "test.jpg"
    photo_file.write_bytes(b"fake jpg")
    photo_id = test_db.add_photo(str(photo_file))

    # Add face with embedding
    embedding = [0.1, 0.2, 0.3] * 128  # 384-dim vector
    face_id = test_db.add_face(
        photo_id=photo_id,
        embedding=embedding,
        bbox=[10, 20, 100, 150],
        confidence=0.95
    )

    assert face_id is not None
    assert face_id > 0

def test_get_faces_by_photo(test_db, tmp_path):
    """Test retrieving faces for a photo."""
    photo_file = tmp_path / "test.jpg"
    photo_file.write_bytes(b"fake jpg")
    photo_id = test_db.add_photo(str(photo_file))

    # Add 2 faces
    embedding1 = [0.1] * 384
    embedding2 = [0.2] * 384
    test_db.add_face(photo_id, embedding1, [10, 20, 100, 150], 0.95)
    test_db.add_face(photo_id, embedding2, [150, 20, 200, 150], 0.88)

    faces = test_db.get_faces_by_photo(photo_id)
    assert len(faces) == 2
    assert faces[0]["confidence"] == 0.95

def test_rosters_table_exists(test_db):
    """Verify rosters table created."""
    cursor = test_db.conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rosters'")
    assert cursor.fetchone() is not None

def test_add_roster_entry(test_db):
    """Test adding roster entry."""
    test_db.add_roster_entry("Test Team", 2026, "16", "Test Player")

    name = test_db.get_player_name("Test Team", 2026, "16")
    assert name == "Test Player"

def test_get_player_name_not_found(test_db):
    """Test lookup when player not found."""
    name = test_db.get_player_name("Unknown Team", 2026, "99")
    assert name is None
