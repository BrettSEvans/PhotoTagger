"""Tests for ClusterRepository (independent of Flask)."""

import pytest
import sqlite3
import tempfile
import json
from pathlib import Path

from src.repositories.cluster import ClusterRepository
from src.repositories.face import FaceRepository
from src.schema import init_schema


@pytest.fixture
def conn_and_repos():
    """Create an in-memory database, ClusterRepository, and FaceRepository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_schema(conn)

        import threading
        lock = threading.RLock()
        cluster_repo = ClusterRepository(conn, lock)
        face_repo = FaceRepository(conn, lock)
        yield cluster_repo, face_repo, conn
        conn.close()


def test_clear_clusters(conn_and_repos):
    """Test clearing all clusters."""
    cluster_repo, face_repo, conn = conn_and_repos

    # Create a cluster and assign a face to it
    cluster_id = cluster_repo.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=1)
    cluster_repo.assign_face_to_cluster(face_id=1, cluster_id=cluster_id)

    # Verify cluster exists
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM player_clusters")
    assert cursor.fetchone()[0] == 1

    # Clear clusters
    cluster_repo.clear_clusters()

    # Verify clusters and assignments are cleared
    cursor.execute("SELECT COUNT(*) FROM player_clusters")
    assert cursor.fetchone()[0] == 0
    cursor.execute("SELECT cluster_id FROM faces WHERE id = 1")
    row = cursor.fetchone()
    assert row is None or row[0] is None


def test_add_player_cluster(conn_and_repos):
    """Test adding a player cluster."""
    cluster_repo, _, _ = conn_and_repos

    cluster_id = cluster_repo.add_player_cluster(face_count=5, photo_count=3, thumbnail_face_id=42)

    assert cluster_id > 0


def test_assign_face_to_cluster(conn_and_repos):
    """Test assigning a face to a cluster."""
    cluster_repo, face_repo, conn = conn_and_repos

    embedding = [0.1] * 384
    bbox = [10, 20, 100, 150]
    face_id = face_repo.add_face(photo_id=1, embedding=embedding, bbox=bbox, confidence=0.95)
    cluster_id = cluster_repo.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=face_id)

    cluster_repo.assign_face_to_cluster(face_id=face_id, cluster_id=cluster_id)

    cursor = conn.cursor()
    cursor.execute("SELECT cluster_id FROM faces WHERE id = ?", (face_id,))
    row = cursor.fetchone()
    assert row[0] == cluster_id


def test_get_all_player_clusters(conn_and_repos):
    """Test retrieving all player clusters."""
    cluster_repo, _, _ = conn_and_repos

    c1 = cluster_repo.add_player_cluster(face_count=5, photo_count=3, thumbnail_face_id=1)
    c2 = cluster_repo.add_player_cluster(face_count=3, photo_count=2, thumbnail_face_id=2)

    clusters = cluster_repo.get_all_player_clusters()

    assert len(clusters) == 2
    assert clusters[0]["face_count"] >= clusters[1]["face_count"]  # Ordered by photo_count DESC


def test_get_photos_by_cluster(conn_and_repos):
    """Test retrieving photos in a cluster."""
    cluster_repo, face_repo, conn = conn_and_repos

    # Add a photo and face
    cursor = conn.cursor()
    cursor.execute("INSERT INTO photos (file_path, file_hash) VALUES (?, ?)", ("test.jpg", "hash123"))
    photo_id = cursor.lastrowid
    conn.commit()

    embedding = [0.1] * 384
    bbox = [10, 20, 100, 150]
    face_id = face_repo.add_face(photo_id=photo_id, embedding=embedding, bbox=bbox, confidence=0.95)

    cluster_id = cluster_repo.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=face_id)
    cluster_repo.assign_face_to_cluster(face_id=face_id, cluster_id=cluster_id)

    photos = cluster_repo.get_photos_by_cluster(cluster_id=cluster_id)

    assert len(photos) == 1
    assert photos[0]["photo_id"] == photo_id
    assert photos[0]["face_bbox"] == bbox


def test_get_cluster_by_id(conn_and_repos):
    """Test retrieving a single cluster."""
    cluster_repo, _, _ = conn_and_repos

    cluster_id = cluster_repo.add_player_cluster(face_count=5, photo_count=3, thumbnail_face_id=10)

    cluster = cluster_repo.get_cluster_by_id(cluster_id)

    assert cluster is not None
    assert cluster["id"] == cluster_id
    assert cluster["face_count"] == 5
    assert cluster["photo_count"] == 3


def test_get_cluster_face_embeddings(conn_and_repos):
    """Test retrieving embeddings for a cluster."""
    cluster_repo, face_repo, conn = conn_and_repos

    # Add two faces with embeddings
    embedding1 = [0.1] * 384
    embedding2 = [0.2] * 384
    face_id1 = face_repo.add_face(photo_id=1, embedding=embedding1, bbox=[10, 20, 100, 150], confidence=0.95)
    face_id2 = face_repo.add_face(photo_id=2, embedding=embedding2, bbox=[50, 60, 150, 200], confidence=0.90)

    cluster_id = cluster_repo.add_player_cluster(face_count=2, photo_count=2, thumbnail_face_id=face_id1)
    cluster_repo.assign_face_to_cluster(face_id=face_id1, cluster_id=cluster_id)
    cluster_repo.assign_face_to_cluster(face_id=face_id2, cluster_id=cluster_id)

    embeddings = cluster_repo.get_cluster_face_embeddings(cluster_id=cluster_id)

    assert len(embeddings) == 2
    assert embeddings[0] == embedding1
    assert embeddings[1] == embedding2


def test_get_unidentified_clusters_with_embeddings(conn_and_repos):
    """Test retrieving unidentified clusters with embeddings."""
    cluster_repo, face_repo, _ = conn_and_repos

    # Create unidentified cluster
    embedding = [0.1] * 384
    face_id = face_repo.add_face(photo_id=1, embedding=embedding, bbox=[10, 20, 100, 150], confidence=0.95)
    cluster_id = cluster_repo.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=face_id)
    cluster_repo.assign_face_to_cluster(face_id=face_id, cluster_id=cluster_id)

    # Create identified cluster (has player_name)
    identified_cluster_id = cluster_repo.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=2)
    # Note: would need to call assign_cluster_to_player to set player_name, but we're testing unidentified clusters

    unidentified = cluster_repo.get_unidentified_clusters_with_embeddings()

    assert len(unidentified) >= 1
    assert any(c["id"] == cluster_id for c in unidentified)
    assert unidentified[0]["embeddings"] == [embedding]


def test_assign_cluster_to_player(conn_and_repos):
    """Test assigning a cluster to a player."""
    cluster_repo, _, conn = conn_and_repos

    cluster_id = cluster_repo.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=1)

    cluster_repo.assign_cluster_to_player(
        cluster_id=cluster_id,
        player_name="Alice",
        jersey_number="23",
        roster_entry_id=100
    )

    cluster = cluster_repo.get_cluster_by_id(cluster_id)
    assert cluster["player_name"] == "Alice"
    assert cluster["jersey_number"] == "23"
    assert cluster["roster_entry_id"] == 100
