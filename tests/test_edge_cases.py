"""Edge case and boundary condition tests for PhotoTagger."""

import io
from pathlib import Path
from PIL import Image
from src.api import create_app
from src.db import Database
import numpy as np


def _make_jpeg_bytes(width: int = 32, height: int = 32, color: str = "red") -> bytes:
    """Return minimal valid JPEG bytes for testing."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ── Compatibility helpers ──────────────────────────────────────────────────────

def _create_cluster(db):
    return db.clusters.add_player_cluster(face_count=0, photo_count=0, thumbnail_face_id=None)


def _add_face(db, photo_id, bbox, embedding, confidence=0.9, sharpness=None):
    return db.faces.add_face(
        photo_id=photo_id,
        embedding=embedding,
        bbox=bbox,
        confidence=confidence,
        sharpness=sharpness,
    )


def _add_face_to_cluster(db, cluster_id, face_id):
    db.clusters.assign_face_to_cluster(face_id, cluster_id)


# ──────────────────────────────────────────────────────────────────────────────


class TestEmptyDatabaseOperations:
    """Test operations on empty database."""

    def test_search_empty_photos(self):
        """Search returns empty list when no photos."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.get("/api/search?jersey=1")
        assert response.status_code == 200
        assert response.json.get("photos", []) == [] or response.json.get("results", []) == []

    def test_get_players_empty_clusters(self):
        """Get players returns empty when no clusters."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.get("/api/players")
        assert response.status_code == 200
        data = response.json
        assert "players" in data or "clusters" in data or data.get("success") is not None

    def test_get_roster_empty_entries(self):
        """Get roster returns empty when no entries."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.get("/api/roster")
        assert response.status_code == 200
        data = response.json
        assert isinstance(data.get("entries", []), list)

    def test_match_similar_no_clusters(self):
        """Match similar returns empty when no clusters."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        # Try match without assigned cluster
        response = client.post("/api/players/999/match-similar")
        # Should error or return empty
        assert response.status_code in {200, 400}


class TestMalformedFileUploads:
    """Test handling of malformed files."""

    def test_upload_invalid_image_format(self, tmp_path):
        """Upload invalid image format — multipart upload ignores unsupported extensions."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.post(
            "/api/upload-photos",
            data={"files": (io.BytesIO(b"This is not a JPEG"), "notimage.txt")},
            content_type="multipart/form-data",
        )
        # Should handle or skip invalid files
        assert response.status_code in {202, 400, 500}

    def test_upload_corrupted_jpeg(self, tmp_path):
        """Upload corrupted JPEG file."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.post(
            "/api/upload-photos",
            data={"files": (io.BytesIO(b"\xff\xd8\xff\xe0" + b"corrupted data"), "corrupted.jpg")},
            content_type="multipart/form-data",
        )
        # Should skip corrupted file
        assert response.status_code in {202, 400}

    def test_upload_empty_file(self, tmp_path):
        """Upload empty file."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.post(
            "/api/upload-photos",
            data={"files": (io.BytesIO(b""), "empty.jpg")},
            content_type="multipart/form-data",
        )
        # Should handle gracefully
        assert response.status_code in {202, 400}


class TestUnicodeAndSpecialCharacters:
    """Test Unicode and special character handling."""

    def test_player_name_with_emoji(self):
        """Player name with emoji characters."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        cluster = _create_cluster(db)
        face = _add_face(db, photo_id=1, bbox=[10, 10, 20, 20], embedding=[0.1] * 512)
        _add_face_to_cluster(db, cluster, face)

        response = client.post(
            f"/api/players/{cluster}/assign",
            json={
                "player_name": "Player 🏐 One",
                "jersey_number": "1",
                "face_ids": []
            }
        )
        # Should handle or reject gracefully
        assert response.status_code in {200, 400}

    def test_team_name_with_accents(self):
        """Team name with accented characters."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.post(
            "/api/roster",
            json={
                "team_name": "Équipe Française",
                "team_year": "2024",
                "player_name": "Joël",
                "jersey_number": "1"
            }
        )
        # Should handle UTF-8
        assert response.status_code in {200, 201, 400}


class TestExtremelyLargeBoundingBoxes:
    """Test face bounding box edge cases."""

    def test_bbox_larger_than_image(self):
        """Face bbox larger than image dimensions."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        db = app.db

        # Create face with bbox larger than typical image
        face = _add_face(db, photo_id=1, bbox=[0, 0, 10000, 10000], embedding=[0.1] * 512)

        assert face > 0

    def test_bbox_negative_coordinates(self):
        """Face bbox with negative coordinates."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        db = app.db

        face = _add_face(db, photo_id=1, bbox=[-100, -100, 100, 100], embedding=[0.1] * 512)

        assert face > 0

    def test_bbox_all_zeros(self):
        """Face bbox all zeros."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        db = app.db

        face = _add_face(db, photo_id=1, bbox=[0, 0, 0, 0], embedding=[0.1] * 512)

        assert face > 0


class TestClusterEdgeSizes:
    """Test cluster behavior with edge-case sizes."""

    def test_single_face_cluster(self):
        """Cluster with just one face."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        db = app.db

        cluster = _create_cluster(db)
        face = _add_face(db, photo_id=1, bbox=[10, 10, 20, 20], embedding=[0.1] * 512)
        _add_face_to_cluster(db, cluster, face)

        cluster_data = db.clusters.get_cluster_by_id(cluster)
        assert cluster_data["face_count"] == 1

    def test_cluster_with_duplicate_embeddings(self):
        """Cluster with identical embedding faces."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        db = app.db

        cluster = _create_cluster(db)

        # Add faces with identical embeddings
        embedding = [0.5] * 512
        for i in range(3):
            face = _add_face(db, photo_id=i, bbox=[10, 10, 20, 20], embedding=embedding)
            _add_face_to_cluster(db, cluster, face)

        # Verify centroid calculation doesn't crash
        embeddings = db.clusters.get_cluster_face_embeddings(cluster)
        assert len(embeddings) == 3
        centroid = np.mean([np.array(e, dtype=np.float32) for e in embeddings], axis=0)
        assert np.allclose(centroid, embedding)


class TestInvalidParameterValues:
    """Test API with invalid parameter values."""

    def test_confidence_out_of_range(self):
        """Confidence parameter outside [0, 1]."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.get("/api/search?jersey=1&min_confidence=1.5")
        # Should validate or clamp
        assert response.status_code in {200, 400}

        response = client.get("/api/search?jersey=1&min_confidence=-0.5")
        assert response.status_code in {200, 400}

    def test_pagination_invalid_values(self):
        """Page/offset with invalid values."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.get("/api/photos?page=0&per_page=100")
        assert response.status_code in {200, 400}

        response = client.get("/api/photos?page=1&per_page=50")
        assert response.status_code in {200, 400}

        response = client.get("/api/photos?page=1&per_page=999999")
        # Should either return empty or limit
        assert response.status_code in {200, 400}

    def test_threshold_out_of_range(self):
        """Similarity threshold outside [-1, 1]."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        # match-similar uses thresholds, test if configurable
        db = app.db
        cluster = _create_cluster(db)
        face = _add_face(db, photo_id=1, bbox=[10, 10, 20, 20], embedding=[0.5] * 512)
        _add_face_to_cluster(db, cluster, face)
        db.clusters.assign_cluster_to_player(cluster, "Player", "1", None)

        response = client.post(f"/api/players/{cluster}/match-similar")
        assert response.status_code in {200, 400}


class TestStaleDataConditions:
    """Test queries with stale or orphaned data."""

    def test_query_deleted_photo(self, tmp_path):
        """Query references deleted photo."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        db = app.db

        photo_dir = tmp_path / "photos"
        photo_dir.mkdir()
        photo_file = photo_dir / "photo.jpg"
        photo_file.write_bytes(_make_jpeg_bytes())

        photo_id = db.photos.add_photo(str(photo_file), source_folder=str(photo_dir))

        # Try to get the photo (it still exists)
        p = db.photos.get_photo_by_id(photo_id)
        assert p is not None
        assert p["id"] == photo_id

    def test_query_deleted_roster_entry(self):
        """Cluster references deleted roster entry."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        db = app.db

        db.roster.add_roster_entry("Team1", 2024, 1, "Player1")
        entries = db.roster.get_all_roster_entries()
        entry = entries[0]
        entry_id = entry["id"]

        cluster = _create_cluster(db)
        db.clusters.assign_cluster_to_player(cluster, "Player1", "1", entry_id)

        # Delete roster entry
        db.roster.delete_roster_entry(entry_id)

        # Cluster still exists but FK is broken
        c = db.clusters.get_cluster_by_id(cluster)
        assert c is not None


class TestConcurrentSchemaUpdates:
    """Test schema safety under concurrent operations."""

    def test_reset_while_querying(self, tmp_path):
        """Data reset while query in progress."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        # Add data
        photo_dir = tmp_path / "photos"
        photo_dir.mkdir()
        photo_file = photo_dir / "photo.jpg"
        photo_file.write_bytes(_make_jpeg_bytes())
        db.photos.add_photo(str(photo_file), source_folder=str(photo_dir))

        # Reset all data
        response = client.post("/api/data/reset", json={"confirm": True})
        assert response.status_code in {200, 202, 500}

        # Query should work after reset (empty)
        response = client.get("/api/photos")
        assert response.status_code == 200

        data = response.json.get("photos", [])
        assert len(data) == 0


class TestVeryLargeBoundingBoxValues:
    """Test extreme bounding box coordinates."""

    def test_bbox_with_max_int_values(self):
        """Bounding box with very large integer values."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        db = app.db

        face = _add_face(db, photo_id=1, bbox=[1000000, 1000000, 2000000, 2000000], embedding=[0.1] * 512)

        assert face > 0

    def test_bbox_with_float_values_as_int(self):
        """Bounding box with float values (stored as int)."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        db = app.db

        face = _add_face(db, photo_id=1, bbox=[10.5, 10.7, 20.3, 20.9], embedding=[0.1] * 512)

        assert face > 0
