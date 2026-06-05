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


def _make_unique_jpeg(index: int) -> bytes:
    """Return unique PNG bytes so file hashes never collide."""
    colour = (index % 256, (index * 7 + 10) % 256, (index * 13 + 20) % 256)
    img = Image.new("RGB", (32, 32), color=colour)
    pixels = img.load()
    pixels[0, 0] = (index % 256, (index * 3) % 256, (index * 17) % 256)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
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
            photo_file.write_bytes(_make_unique_jpeg(i))
            photo_dirs.append(str(photo_dir))

        # Upload each directory concurrently via multipart
        job_ids = []
        errors = []

        def upload(index, photo_dir):
            try:
                # Read the unique image for this dir
                photo_file = Path(photo_dir) / f"photo_{index}.jpg"
                response = client.post(
                    "/api/upload-photos",
                    data={"files": (io.BytesIO(photo_file.read_bytes()), f"photo_{index}.jpg")},
                    content_type="multipart/form-data",
                )
                if response.status_code != 202:
                    errors.append(f"Upload failed: {response.status_code}")
                    return
                job_id = response.json["job_id"]
                job_ids.append(job_id)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=upload, args=(i, d)) for i, d in enumerate(photo_dirs)]
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
        """Concurrent uploads of same photo don't create duplicates."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        # Create a single photo
        photo_dir = tmp_path / "photos"
        photo_dir.mkdir()
        photo_file = photo_dir / "photo.jpg"
        photo_bytes = _make_jpeg_bytes()
        photo_file.write_bytes(photo_bytes)

        # Try uploading same file from 3 threads simultaneously
        job_ids = []
        errors = []

        def upload():
            try:
                response = client.post(
                    "/api/upload-photos",
                    data={"files": (io.BytesIO(photo_bytes), "photo.jpg")},
                    content_type="multipart/form-data",
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

        # Should have only 1 photo (hash-based dedup)
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

        # Set up test data: create 5 clusters
        cluster_ids = []
        for i in range(5):
            face_id = _add_face(db, photo_id=i, bbox=[10, 10, 20, 20], embedding=[0.1] * 512)
            cluster_id = _create_cluster(db)
            _add_face_to_cluster(db, cluster_id, face_id)
            cluster_ids.append(cluster_id)

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
        clusters = db.clusters.get_all_player_clusters()
        assigned = [c for c in clusters if c["player_name"]]
        assert len(assigned) >= 5

    def test_concurrent_assignments_same_cluster_last_wins(self, tmp_path):
        """When same cluster assigned concurrently, last assignment wins."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()
        db = app.db

        # Create one cluster
        cluster_id = _create_cluster(db)
        face_id = _add_face(db, photo_id=1, bbox=[10, 10, 20, 20], embedding=[0.1] * 512)
        _add_face_to_cluster(db, cluster_id, face_id)

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
        cluster_id = _create_cluster(db)
        face_id = _add_face(db, photo_id=1, bbox=[10, 10, 20, 20], embedding=[0.1] * 512)
        _add_face_to_cluster(db, cluster_id, face_id)
        db.clusters.assign_cluster_to_player(cluster_id, "Player1", "1", None)

        # Create unidentified cluster for matching
        unid_cluster = _create_cluster(db)
        unid_face = _add_face(db, photo_id=2, bbox=[10, 10, 20, 20], embedding=[0.1] * 512)
        _add_face_to_cluster(db, unid_cluster, unid_face)

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
            photo_file.write_bytes(_make_unique_jpeg(i))

        job_ids = []
        errors = []

        def submit_crawl():
            try:
                response = client.post(
                    "/api/crawl",
                    json={"photo_dir": str(photo_dir)}
                )
                if response.status_code == 202:
                    job_ids.append(response.json["job_id"])
                else:
                    errors.append(f"Crawl failed: {response.status_code}")
            except Exception as e:
                errors.append(f"Crawl error: {str(e)}")

        def submit_detect():
            try:
                # detect-faces requires game context and json body
                db.context.set_game_context([
                    {"team_name": "Team1", "team_year": 2024, "uniform_color": "red"},
                    {"team_name": "Team2", "team_year": 2024, "uniform_color": "blue"},
                ])
                response = client.post("/api/detect-faces", json={})
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
                    json={"photo_dir": str(photo_dir)}
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
                if response.status_code in {200, 201}:
                    # API may return 201 without entry id — fetch last entry
                    entries = db.roster.get_all_roster_entries()
                    for e in reversed(entries):
                        if e["player_name"] == player_name:
                            roster_ids.append(e["id"])
                            break
                else:
                    errors.append(f"Add entry failed: {response.status_code} {response.json}")
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
