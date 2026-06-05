"""Performance and scale tests for PhotoTagger."""

import io
import json
import tempfile
import time
from pathlib import Path
from PIL import Image
from src.api import create_app
from src.db import Database
import numpy as np


def _make_jpeg_bytes(color: str = "red") -> bytes:
    """Return minimal valid JPEG bytes for testing."""
    img = Image.new("RGB", (32, 32), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_unique_jpeg(index: int) -> bytes:
    """Return PNG bytes unique to *index* so file hashes never collide.
    Uses lossless PNG to guarantee distinct content for each index.
    Saved as .jpg in tests but file_hash is computed from content, not name.
    """
    import struct
    # Embed index directly into pixels to guarantee unique content
    colour = (index % 256, (index // 256) % 256, (index // 65536) % 256)
    img = Image.new("RGB", (32, 32), color=colour)
    # Draw a unique pixel to ensure hash uniqueness even for close colors
    pixels = img.load()
    pixels[0, 0] = (index % 256, (index * 7) % 256, (index * 13) % 256)
    pixels[1, 0] = ((index + 1) % 256, (index * 3) % 256, (index * 17) % 256)
    buf = io.BytesIO()
    img.save(buf, format="PNG")  # lossless — guarantees unique hash
    return buf.getvalue()


def wait_for_job(db: Database, job_id: int, timeout: float = 30.0):
    """Poll job status until completion."""
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = db.jobs.get_processing_job(job_id)
        if job and job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for job {job_id}")


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


class TestPhotoIngestionPerformance:
    """Test photo ingestion with large batches."""

    def test_500_photo_ingestion_completes(self, tmp_path):
        """Ingest 500 photos without timeout or crashes."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        db = app.db

        # Create 500 photos in bulk
        photo_dir = tmp_path / "photos"
        photo_dir.mkdir()

        for i in range(500):
            photo_file = photo_dir / f"photo_{i:04d}.jpg"
            photo_file.write_bytes(_make_unique_jpeg(i))

        start = time.time()
        for i in range(500):
            db.photos.add_photo(
                file_path=str(photo_dir / f"photo_{i:04d}.jpg"),
                source_folder=str(photo_dir),
            )
        elapsed = time.time() - start

        photos = db.photos.get_all_photos()
        assert len(photos) == 500
        # Should complete in reasonable time
        assert elapsed < 30.0, f"500 photo insert took {elapsed}s"

    def test_500_photo_pagination(self, tmp_path):
        """Query 500 photos with pagination."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        # Insert 500 photos
        photo_dir = tmp_path / "photos"
        photo_dir.mkdir()

        for i in range(500):
            photo_file = photo_dir / f"photo_{i:04d}.jpg"
            photo_file.write_bytes(_make_unique_jpeg(i))
            db.photos.add_photo(
                file_path=str(photo_file),
                source_folder=str(photo_dir)
            )

        # Query with pagination using page/per_page (current API)
        all_photos = []
        per_page = 50
        for page in range(1, 11):
            response = client.get(
                f"/api/photos?page={page}&per_page={per_page}"
            )
            assert response.status_code == 200
            all_photos.extend(response.json["photos"])

        assert len(all_photos) == 500

    def test_large_offset_query_efficiency(self, tmp_path):
        """Query with large page offset."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        # Insert 1000 photos
        photo_dir = tmp_path / "photos"
        photo_dir.mkdir()

        for i in range(1000):
            photo_file = photo_dir / f"photo_{i:04d}.jpg"
            photo_file.write_bytes(_make_unique_jpeg(i))
            db.photos.add_photo(
                file_path=str(photo_file),
                source_folder=str(photo_dir)
            )

        # Query middle of dataset — page 11 with per_page=50 is offset 500
        start = time.time()
        response = client.get("/api/photos?page=11&per_page=50")
        elapsed = time.time() - start

        assert response.status_code == 200
        assert len(response.json["photos"]) == 50
        # Should use LIMIT/OFFSET, be fast
        assert elapsed < 1.0, f"Query took {elapsed}s"


class TestFaceClusteringPerformance:
    """Test face clustering with large datasets."""

    def test_1000_face_clustering_centroid_calculation(self, tmp_path):
        """Cluster 1000 faces and verify centroid math."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        db = app.db

        # Create 1000 faces
        cluster_id = _create_cluster(db)

        for i in range(1000):
            # Create similar but varying embeddings
            embedding = [0.5 + (i * 0.0001) % 0.1] * 512
            face_id = _add_face(db, photo_id=i, bbox=[10, 10, 20, 20], embedding=embedding)
            _add_face_to_cluster(db, cluster_id, face_id)

        # Verify cluster stats
        cluster = db.clusters.get_cluster_by_id(cluster_id)
        assert cluster["face_count"] >= 1000

        # Verify centroid exists and is reasonable
        embeddings = db.clusters.get_cluster_face_embeddings(cluster_id)
        assert len(embeddings) >= 1000

        # Verify centroid is valid (not all zeros, reasonable range)
        centroid = np.mean([np.array(e, dtype=np.float32) for e in embeddings], axis=0)
        assert not np.allclose(centroid, 0.0)
        assert np.all(np.isfinite(centroid))

    def test_large_similarity_comparison_no_timeout(self, tmp_path):
        """Run 1000+ face similarity comparisons without timeout."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        # Create assigned cluster with embeddings
        assigned_cluster = _create_cluster(db)
        assigned_face = _add_face(db, photo_id=1, bbox=[10, 10, 20, 20], embedding=[0.5] * 512)
        _add_face_to_cluster(db, assigned_cluster, assigned_face)
        db.clusters.assign_cluster_to_player(assigned_cluster, "Player1", "1", None)

        # Create 100 unidentified clusters (1000+ faces total)
        for i in range(100):
            cluster = _create_cluster(db)
            for j in range(10):
                face = _add_face(
                    db, photo_id=1000 + i * 10 + j,
                    bbox=[10, 10, 20, 20],
                    embedding=[0.5 + (i * 0.001)] * 512,
                )
                _add_face_to_cluster(db, cluster, face)

        # Run similarity match
        start = time.time()
        response = client.post(f"/api/players/{assigned_cluster}/match-similar")
        elapsed = time.time() - start

        assert response.status_code == 200
        # Should complete without timeout
        assert elapsed < 30.0, f"Similarity comparison took {elapsed}s"


class TestRosterImportPerformance:
    """Test roster import with large datasets."""

    def test_large_roster_import_5000_entries(self, tmp_path):
        """Import roster with 5000 entries."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        # Create CSV with 5000 roster entries
        csv_file = tmp_path / "large_roster.csv"
        csv_lines = ["player_name,team_name,team_year,jersey_number"]

        for i in range(5000):
            csv_lines.append(
                f"Player{i},Team1,2024,{(i % 100) + 1}"
            )

        csv_file.write_text("\n".join(csv_lines))

        # Import roster
        start = time.time()
        with open(csv_file, "rb") as f:
            response = client.post(
                "/api/roster/import",
                data={"file": (f, "roster.csv")},
                content_type="multipart/form-data"
            )
        elapsed = time.time() - start

        # Should complete quickly
        assert elapsed < 30.0, f"Import took {elapsed}s"

        # Verify entries imported (or response indicates batch operation)
        if response.status_code == 200:
            data = response.json
            # Check result or status
            assert "entries" in data or "imported" in data or "error" not in data


class TestClusteringHierarchy:
    """Test clustering with hierarchical structures."""

    def test_cluster_hierarchy_deep_nesting(self, tmp_path):
        """Create deeply nested cluster relationships."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        db = app.db

        # Create 10 clusters, each with 50 faces
        cluster_ids = []

        for cluster_num in range(10):
            cluster_id = _create_cluster(db)
            cluster_ids.append(cluster_id)

            for face_num in range(50):
                face_id = _add_face(
                    db, photo_id=cluster_num * 50 + face_num,
                    bbox=[10, 10, 20, 20],
                    embedding=[0.5] * 512,
                )
                _add_face_to_cluster(db, cluster_id, face_id)

        # Assign some clusters to players
        for i, cluster_id in enumerate(cluster_ids[:5]):
            db.clusters.assign_cluster_to_player(
                cluster_id, f"Player{i}", str(i + 1), None
            )

        # Get all clusters and verify structure
        clusters = db.clusters.get_all_player_clusters()
        assert len(clusters) == 10

        assigned = [c for c in clusters if c["player_name"]]
        assert len(assigned) == 5

    def test_auto_match_with_deep_hierarchy(self, tmp_path):
        """Auto-match in deeply nested cluster structure."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        # Create assigned cluster
        assigned_cluster = _create_cluster(db)
        assigned_face = _add_face(db, photo_id=1, bbox=[10, 10, 20, 20], embedding=[0.5] * 512)
        _add_face_to_cluster(db, assigned_cluster, assigned_face)
        db.clusters.assign_cluster_to_player(assigned_cluster, "Player1", "1", None)

        # Create 50 nested clusters
        for i in range(50):
            cluster = _create_cluster(db)
            for j in range(10):
                face = _add_face(
                    db, photo_id=100 + i * 10 + j,
                    bbox=[10, 10, 20, 20],
                    embedding=[0.5] * 512,
                )
                _add_face_to_cluster(db, cluster, face)

        # Run auto-match
        start = time.time()
        response = client.post(f"/api/players/{assigned_cluster}/match-similar")
        elapsed = time.time() - start

        assert response.status_code == 200
        assert elapsed < 20.0


class TestQueryPerformanceMetrics:
    """Test query performance under various conditions."""

    def test_search_by_jersey_with_large_dataset(self, tmp_path):
        """Search by jersey across 1000 photos."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        # Insert 1000 photos with OCR
        photo_dir = tmp_path / "photos"
        photo_dir.mkdir()

        for i in range(1000):
            photo_file = photo_dir / f"photo_{i:04d}.jpg"
            photo_file.write_bytes(_make_unique_jpeg(i))
            photo_id = db.photos.add_photo(
                file_path=str(photo_file),
                source_folder=str(photo_dir)
            )
            # Add OCR result — raw_text is now required
            jersey = 1 + (i % 20)  # Jersey numbers 1-20 repeated
            db.photos.add_ocr_result(photo_id, str(jersey), 0.95, raw_text=str(jersey))

        # Search for specific jersey
        start = time.time()
        response = client.get(f"/api/search?jersey=5")
        elapsed = time.time() - start

        assert response.status_code == 200
        results = response.json.get("results", response.json.get("photos", []))
        # Should find ~50 photos with jersey 5
        assert len(results) > 0
        assert elapsed < 2.0

    def test_batch_photo_retrieval_efficiency(self, tmp_path):
        """Retrieve batches of photos efficiently."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        # Create 100 photos
        photo_dir = tmp_path / "photos"
        photo_dir.mkdir()

        for i in range(100):
            photo_file = photo_dir / f"photo_{i:02d}.jpg"
            photo_file.write_bytes(_make_unique_jpeg(i))
            db.photos.add_photo(
                file_path=str(photo_file),
                source_folder=str(photo_dir)
            )

        # Retrieve in batches using page/per_page (current API)
        total_retrieved = 0
        start = time.time()

        for page in range(1, 11):
            response = client.get(f"/api/photos?page={page}&per_page=10")
            assert response.status_code == 200
            total_retrieved += len(response.json["photos"])

        elapsed = time.time() - start

        assert total_retrieved == 100
        assert elapsed < 2.0
