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


def test_deassign_faces_deletes_empty_cluster(test_db, tmp_path):
    """Removing the last face from a cluster should delete the empty cluster."""
    photo_file = tmp_path / "test.jpg"
    photo_file.write_bytes(b"fake jpg")
    photo_id = test_db.add_photo(str(photo_file))
    face_id = test_db.add_face(photo_id, [0.1] * 384, [10, 20, 100, 150], 0.95)
    cluster_id = test_db.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=face_id)
    test_db.assign_face_to_cluster(face_id, cluster_id)

    result = test_db.deassign_faces([face_id])

    assert result["deassigned"] == 1
    assert result["deleted_cluster_ids"] == [cluster_id]
    assert test_db.get_all_player_clusters() == []


def test_deassign_faces_updates_cluster_counts(test_db, tmp_path):
    """Removing one face from a multi-face cluster should refresh counts and thumbnail."""
    photo_file1 = tmp_path / "one.jpg"
    photo_file2 = tmp_path / "two.jpg"
    photo_file1.write_bytes(b"fake jpg one")
    photo_file2.write_bytes(b"fake jpg two")
    photo_id1 = test_db.add_photo(str(photo_file1))
    photo_id2 = test_db.add_photo(str(photo_file2))
    face_id1 = test_db.add_face(photo_id1, [0.1] * 384, [10, 20, 100, 150], 0.95)
    face_id2 = test_db.add_face(photo_id2, [0.2] * 384, [20, 30, 110, 160], 0.88)
    cluster_id = test_db.add_player_cluster(face_count=2, photo_count=2, thumbnail_face_id=face_id1)
    test_db.assign_face_to_cluster(face_id1, cluster_id)
    test_db.assign_face_to_cluster(face_id2, cluster_id)

    result = test_db.deassign_faces([face_id1])

    assert result["deleted_cluster_ids"] == []
    cluster = test_db.get_all_player_clusters()[0]
    assert cluster["id"] == cluster_id
    assert cluster["face_count"] == 1
    assert cluster["photo_count"] == 1
    assert cluster["thumbnail_face_id"] == face_id2

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
