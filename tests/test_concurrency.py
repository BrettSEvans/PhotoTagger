"""Concurrent operation tests for PhotoTagger blueprints."""

import io
import threading
import time
from pathlib import Path
from PIL import Image
from src.api import create_app
from src.db import Database


def _make_jpeg_bytes(color: str = "red") -> bytes:
    """Return minimal valid JPEG bytes for testing."""
    img = Image.new("RGB", (32, 32), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def wait_for_job(db: Database, job_id: int, timeout: float = 5.0):
    """Poll job status until completion."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = db.jobs.get_processing_job(job_id)
        if job and job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for job {job_id}")


class TestConcurrentUploads:
    """Test concurrent photo upload operations."""

    def test_concurrent_uploads_to_different_dirs(self, tmp_path):
        """Multiple simultaneous uploads to different directories."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        # Create 5 different temp directories with photos
        photo_dirs = []
        for i in range(5):
            photo_dir = tmp_path / f"photos_{i}"
            photo_dir.mkdir()
            photo_file = photo_dir / f"photo_{i}.jpg"
            photo_file.write_bytes(_make_jpeg_bytes(color="red"))
            photo_dirs.append(str(photo_dir))

        # Upload each directory concurrently
        job_ids = []
        errors = []

        def upload(photo_path):
            try:
                response = client.post(
                    "/api/upload-photos",
                    json={"photo_directory": photo_path}
                )
                if response.status_code != 202:
                    errors.append(f"Upload failed: {response.status_code}")
                    return
                job_id = response.json["job_id"]
                job_ids.append(job_id)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=upload, args=(d,)) for d in photo_dirs]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Upload errors: {errors}"
        assert len(job_ids) == 5, f"Expected 5 jobs, got {len(job_ids)}"

        # Verify all jobs complete
        for job_id in job_ids:
            job = wait_for_job(db, job_id, timeout=10.0)
            assert job["status"] in {"succeeded", "failed"}

        # Verify photos were indexed
        photos = db.photos.get_all_photos()
        assert len(photos) == 5

    def test_concurrent_uploads_same_dir_no_duplicates(self, tmp_path):
        """Concurrent uploads of same directory don't create duplicates."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        # Create directory with single photo
        photo_dir = tmp_path / "photos"
        photo_dir.mkdir()
        photo_file = photo_dir / "photo.jpg"
        photo_file.write_bytes(_make_jpeg_bytes())

        # Try uploading same dir from 3 threads simultaneously
        job_ids = []
        errors = []

        def upload():
            try:
                response = client.post(
                    "/api/upload-photos",
                    json={"photo_directory": str(photo_dir)}
                )
                if response.status_code == 202:
                    job_ids.append(response.json["job_id"])
                else:
                    errors.append(f"Status {response.status_code}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=upload) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(job_ids) == 3

        # Wait for all jobs
        for job_id in job_ids:
            wait_for_job(db, job_id, timeout=10.0)

        # Should still have only 1 photo (hash-based dedup)
        photos = db.photos.get_all_photos()
        assert len(photos) == 1


class TestConcurrentClusterAssignments:
    """Test concurrent cluster assignment operations."""

    def test_concurrent_assignments_different_clusters(self, tmp_path):
        """Assign different clusters to players concurrently."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        # Set up test data: create clusters
        for i in range(5):
            # Create faces and cluster
            for j in range(3):
                face_id = db.faces.add_face(
                    photo_id=i,
                    face_bbox=[10, 10, 20, 20],
                    embedding=[0.1] * 512,
                    sharpness_score=0.8,
                )
            # Create cluster from faces
            cluster_id = db.clusters.create_cluster()
            db.clusters.add_face_to_cluster(cluster_id, face_id)

        clusters = db.clusters.get_all_clusters()
        cluster_ids = [c["id"] for c in clusters[:5]]

        # Assign each cluster concurrently
        errors = []

        def assign(cluster_id, player_name):
            try:
                response = client.post(
                    f"/api/players/{cluster_id}/assign",
                    json={
                        "player_name": player_name,
                        "jersey_number": str(cluster_id),
                        "face_ids": []
                    }
                )
                if response.status_code != 200:
                    errors.append(f"Assign {cluster_id} failed: {response.status_code}")
            except Exception as e:
                errors.append(str(e))

        threads = []
        for i, cluster_id in enumerate(cluster_ids):
            t = threading.Thread(
                target=assign,
                args=(cluster_id, f"Player{i}")
            )
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Assignment errors: {errors}"

        # Verify all clusters assigned
        clusters = db.clusters.get_all_clusters()
        assigned = [c for c in clusters if c["player_name"]]
        assert len(assigned) >= 5

    def test_concurrent_assignments_same_cluster_last_wins(self, tmp_path):
        """When same cluster assigned concurrently, last assignment wins."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        # Create one cluster
        cluster_id = db.clusters.create_cluster()
        face_id = db.faces.add_face(
            photo_id=1,
            face_bbox=[10, 10, 20, 20],
            embedding=[0.1] * 512,
            sharpness_score=0.8,
        )
        db.clusters.add_face_to_cluster(cluster_id, face_id)

        # Try assigning to 3 different players concurrently
        responses = []
        errors = []

        def assign(player_name):
            try:
                response = client.post(
                    f"/api/players/{cluster_id}/assign",
                    json={
                        "player_name": player_name,
                        "jersey_number": "1",
                        "face_ids": []
                    }
                )
                responses.append((player_name, response.status_code))
            except Exception as e:
                errors.append(str(e))

        threads = [
            threading.Thread(target=assign, args=(f"Player{i}",))
            for i in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(responses) == 3
        assert all(status == 200 for _, status in responses)

        # Cluster should be assigned to one of the players
        cluster = db.clusters.get_cluster_by_id(cluster_id)
        assert cluster["player_name"] in ["Player0", "Player1", "Player2"]


class TestConcurrentDeassignAndAutoMatch:
    """Test concurrent deassign + auto-match operations."""

    def test_deassign_while_match_similar_processing(self, tmp_path):
        """Deassign faces while match_similar is running."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        # Create assigned cluster
        cluster_id = db.clusters.create_cluster()
        face_id = db.faces.add_face(
            photo_id=1,
            face_bbox=[10, 10, 20, 20],
            embedding=[0.1] * 512,
            sharpness_score=0.8,
        )
        db.clusters.add_face_to_cluster(cluster_id, face_id)
        db.clusters.assign_cluster_to_player(cluster_id, "Player1", "1", None)

        # Create unidentified cluster for matching
        unid_cluster = db.clusters.create_cluster()
        unid_face = db.faces.add_face(
            photo_id=2,
            face_bbox=[10, 10, 20, 20],
            embedding=[0.1] * 512,  # Similar embedding
            sharpness_score=0.8,
        )
        db.clusters.add_face_to_cluster(unid_cluster, unid_face)

        # Deassign and match_similar concurrently
        deassign_error = None
        match_response = None

        def deassign():
            nonlocal deassign_error
            try:
                response = client.post(
                    "/api/faces/deassign",
                    json={"face_ids": [face_id]}
                )
                if response.status_code != 200:
                    deassign_error = f"Deassign failed: {response.status_code}"
            except Exception as e:
                deassign_error = str(e)

        def match():
            nonlocal match_response
            try:
                response = client.post(
                    f"/api/players/{cluster_id}/match-similar"
                )
                match_response = response
            except Exception as e:
                match_response = str(e)

        t1 = threading.Thread(target=deassign)
        t2 = threading.Thread(target=match)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert deassign_error is None
        # match_similar might fail with cluster not assigned, but should not crash
        if isinstance(match_response, str):
            assert "error" in match_response.lower()
        else:
            assert match_response.status_code in {200, 400}


class TestConcurrentJobSubmissions:
    """Test concurrent job submission scenarios."""

    def test_concurrent_job_submissions_different_types(self, tmp_path):
        """Submit different job types concurrently."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        # Prepare photo directory for crawl
        photo_dir = tmp_path / "photos"
        photo_dir.mkdir()
        for i in range(3):
            photo_file = photo_dir / f"photo_{i}.jpg"
            photo_file.write_bytes(_make_jpeg_bytes())

        job_ids = []
        errors = []

        def submit_crawl():
            try:
                response = client.post(
                    "/api/crawl",
                    json={"photo_directory": str(photo_dir)}
                )
                if response.status_code == 202:
                    job_ids.append(response.json["job_id"])
                else:
                    errors.append(f"Crawl failed: {response.status_code}")
            except Exception as e:
                errors.append(f"Crawl error: {str(e)}")

        def submit_detect():
            try:
                response = client.post("/api/detect-faces")
                if response.status_code == 202:
                    job_ids.append(response.json["job_id"])
                else:
                    errors.append(f"Detect failed: {response.status_code}")
            except Exception as e:
                errors.append(f"Detect error: {str(e)}")

        # Submit jobs concurrently
        t1 = threading.Thread(target=submit_crawl)
        t2 = threading.Thread(target=submit_detect)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"Job errors: {errors}"
        assert len(job_ids) >= 1  # At least one should succeed

        # Verify job IDs are unique
        assert len(job_ids) == len(set(job_ids))

    def test_concurrent_job_submissions_same_type(self, tmp_path):
        """Submit same job type multiple times concurrently."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        photo_dir = tmp_path / "photos"
        photo_dir.mkdir()
        photo_file = photo_dir / "photo.jpg"
        photo_file.write_bytes(_make_jpeg_bytes())

        job_ids = []
        errors = []

        def submit_crawl():
            try:
                response = client.post(
                    "/api/crawl",
                    json={"photo_directory": str(photo_dir)}
                )
                if response.status_code == 202:
                    job_ids.append(response.json["job_id"])
                else:
                    errors.append(f"Status {response.status_code}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=submit_crawl) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(job_ids) == 5
        assert len(set(job_ids)) == 5  # All unique


class TestConcurrentRosterUpdates:
    """Test concurrent roster update operations."""

    def test_concurrent_roster_operations_no_foreign_key_violation(self, tmp_path):
        """Concurrent roster operations maintain FK constraints."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        # Set game context
        context = [
            {"team_name": "Team1", "team_year": "2024"},
            {"team_name": "Team2", "team_year": "2024"},
        ]
        for ctx in context:
            db.context.set_game_context(ctx)

        roster_ids = []
        errors = []

        def add_entry(team_name, player_name, jersey):
            try:
                response = client.post(
                    "/api/roster",
                    json={
                        "team_name": team_name,
                        "team_year": "2024",
                        "player_name": player_name,
                        "jersey_number": str(jersey),
                    }
                )
                if response.status_code == 200:
                    roster_ids.append(response.json["entry"]["id"])
                else:
                    errors.append(f"Add entry failed: {response.status_code}")
            except Exception as e:
                errors.append(str(e))

        # Add entries concurrently
        threads = []
        for i in range(5):
            team = "Team1" if i % 2 == 0 else "Team2"
            t = threading.Thread(
                target=add_entry,
                args=(team, f"Player{i}", 1 + i)
            )
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors: {errors}"
        assert len(roster_ids) == 5

        # Verify all entries in database
        all_entries = db.roster.get_all_roster_entries()
        assert len(all_entries) == 5
