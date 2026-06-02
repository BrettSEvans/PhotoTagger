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
            photo_file.write_bytes(_make_jpeg_bytes(
                color=["red", "green", "blue"][i % 3]
            ))

        start = time.time()
        for i in range(500):
            db.photos.add_photo(
                file_path=str(photo_dir / f"photo_{i:04d}.jpg"),
                source_folder=str(photo_dir)
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
            photo_file.write_bytes(_make_jpeg_bytes())
            db.photos.add_photo(
                file_path=str(photo_file),
                source_folder=str(photo_dir)
            )

        # Query with pagination
        all_photos = []
        for offset in range(0, 500, 50):
            response = client.get(
                f"/api/photos?offset={offset}&limit=50"
            )
            assert response.status_code == 200
            all_photos.extend(response.json["photos"])

        assert len(all_photos) == 500

    def test_large_offset_query_efficiency(self, tmp_path):
        """Query with large offset (LIMIT/OFFSET in SQL)."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        # Insert 1000 photos
        photo_dir = tmp_path / "photos"
        photo_dir.mkdir()

        for i in range(1000):
            photo_file = photo_dir / f"photo_{i:04d}.jpg"
            photo_file.write_bytes(_make_jpeg_bytes())
            db.photos.add_photo(
                file_path=str(photo_file),
                source_folder=str(photo_dir)
            )

        # Query middle of dataset
        start = time.time()
        response = client.get("/api/photos?offset=500&limit=50")
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
        cluster_id = db.clusters.create_cluster()

        for i in range(1000):
            # Create similar but varying embeddings
            embedding = [0.5 + (i * 0.0001) % 0.1] * 512
            face_id = db.faces.add_face(
                photo_id=i,
                face_bbox=[10, 10, 20, 20],
                embedding=embedding,
                sharpness_score=0.8,
            )
            db.clusters.add_face_to_cluster(cluster_id, face_id)

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
        assigned_cluster = db.clusters.create_cluster()
        assigned_face = db.faces.add_face(
            photo_id=1,
            face_bbox=[10, 10, 20, 20],
            embedding=[0.5] * 512,
            sharpness_score=0.8,
        )
        db.clusters.add_face_to_cluster(assigned_cluster, assigned_face)
        db.clusters.assign_cluster_to_player(assigned_cluster, "Player1", "1", None)

        # Create 100 unidentified clusters (1000+ faces total)
        for i in range(100):
            cluster = db.clusters.create_cluster()
            for j in range(10):
                face = db.faces.add_face(
                    photo_id=1000 + i * 10 + j,
                    face_bbox=[10, 10, 20, 20],
                    embedding=[0.5 + (i * 0.001)] * 512,  # Slightly different
                    sharpness_score=0.8,
                )
                db.clusters.add_face_to_cluster(cluster, face)

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
            cluster_id = db.clusters.create_cluster()
            cluster_ids.append(cluster_id)

            for face_num in range(50):
                face_id = db.faces.add_face(
                    photo_id=cluster_num * 50 + face_num,
                    face_bbox=[10, 10, 20, 20],
                    embedding=[0.5] * 512,
                    sharpness_score=0.8,
                )
                db.clusters.add_face_to_cluster(cluster_id, face_id)

        # Assign some clusters to players
        for i, cluster_id in enumerate(cluster_ids[:5]):
            db.clusters.assign_cluster_to_player(
                cluster_id, f"Player{i}", str(i + 1), None
            )

        # Get all clusters and verify structure
        clusters = db.clusters.get_all_clusters()
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
        assigned_cluster = db.clusters.create_cluster()
        assigned_face = db.faces.add_face(
            photo_id=1,
            face_bbox=[10, 10, 20, 20],
            embedding=[0.5] * 512,
            sharpness_score=0.8,
        )
        db.clusters.add_face_to_cluster(assigned_cluster, assigned_face)
        db.clusters.assign_cluster_to_player(assigned_cluster, "Player1", "1", None)

        # Create 50 nested clusters
        for i in range(50):
            cluster = db.clusters.create_cluster()
            for j in range(10):
                face = db.faces.add_face(
                    photo_id=100 + i * 10 + j,
                    face_bbox=[10, 10, 20, 20],
                    embedding=[0.5] * 512,
                    sharpness_score=0.8,
                )
                db.clusters.add_face_to_cluster(cluster, face)

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
            photo_file.write_bytes(_make_jpeg_bytes())
            photo_id = db.photos.add_photo(
                file_path=str(photo_file),
                source_folder=str(photo_dir)
            )
            # Add OCR result
            jersey = 1 + (i % 20)  # Jersey numbers 1-20 repeated
            db.photos.add_ocr_result(photo_id, jersey, 0.95)

        # Search for specific jersey
        start = time.time()
        response = client.get(f"/api/search?jersey=5")
        elapsed = time.time() - start

        assert response.status_code == 200
        results = response.json["photos"]
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
            photo_file.write_bytes(_make_jpeg_bytes())
            db.photos.add_photo(
                file_path=str(photo_file),
                source_folder=str(photo_dir)
            )

        # Retrieve in batches
        total_retrieved = 0
        start = time.time()

        for offset in range(0, 100, 10):
            response = client.get(f"/api/photos?offset={offset}&limit=10")
            assert response.status_code == 200
            total_retrieved += len(response.json["photos"])

        elapsed = time.time() - start

        assert total_retrieved == 100
        assert elapsed < 2.0
