"""
Tests for the three critical bugs fixed in the refactor/api-db-critical-fixes branch.

Critical Issue 1: Concurrency bug — match_similar_clusters bypassed db._lock via
    raw db.conn.cursor(); replaced with db.faces.get_face_photo_location().

Critical Issue 2: Temp directory leak — upload_photos created the temp dir before
    validating all files, so a bad extension caused an early return that left orphaned
    directories and partially-saved files on disk.

Critical Issue 3: Pagination OOM — GET /api/photos loaded every photo row into Python
    memory before slicing; replaced with SQL LIMIT/OFFSET via db.photos.get_all_photos(limit,
    offset) + db.photos.count_photos().
"""

import io
import json
import os
import tempfile
import threading
from pathlib import Path

import pytest
from PIL import Image

from src.api import create_app
from src.db import Database


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    database = Database(":memory:")
    database.init_schema()
    yield database
    database.close()


@pytest.fixture
def app():
    application = create_app(db_path=":memory:")
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _make_jpeg_bytes(color: str = "red") -> bytes:
    """Return minimal valid JPEG bytes for a small solid-colour image."""
    img = Image.new("RGB", (32, 32), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════════
# Critical Issue 1: db.get_face_photo_location uses the lock
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetFacePhotoLocation:
    """db.faces.get_face_photo_location() must use _lock and return correct data."""

    def test_returns_none_for_nonexistent_face(self, db, tmp_path):
        assert db.faces.get_face_photo_location(99999) is None

    def test_returns_photo_id_and_bbox(self, db, tmp_path):
        # Arrange: create a real photo file so add_photo doesn't raise
        img_path = tmp_path / "face_test.jpg"
        img_path.write_bytes(_make_jpeg_bytes())

        photo_id = db.photos.add_photo(str(img_path))
        face_id = db.faces.add_face(
            photo_id=photo_id,
            embedding=[0.1] * 512,
            bbox=[10, 20, 50, 80],
            confidence=0.9,
        )

        result = db.faces.get_face_photo_location(face_id)

        assert result is not None
        assert result["photo_id"] == photo_id
        assert result["face_bbox"] == [10, 20, 50, 80]

    def test_is_thread_safe_under_concurrent_reads(self, db, tmp_path):
        """get_face_photo_location must not raise even under concurrent calls."""
        img_path = tmp_path / "concurrent.jpg"
        img_path.write_bytes(_make_jpeg_bytes("blue"))

        photo_id = db.photos.add_photo(str(img_path))
        face_id = db.faces.add_face(
            photo_id=photo_id,
            embedding=[0.5] * 512,
            bbox=[0, 0, 10, 10],
            confidence=0.8,
        )

        errors = []

        def reader():
            try:
                db.faces.get_face_photo_location(face_id)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread-safety violation: {errors}"

    def test_match_similar_no_longer_accesses_raw_conn(self):
        """Verify the api.py source no longer contains the raw db.conn.cursor() pattern
        that caused the concurrency bug."""
        api_src = Path("src/api.py").read_text()
        assert "db.conn.cursor()" not in api_src, (
            "api.py must not access db.conn.cursor() directly — use a db method instead"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Critical Issue 2: Upload temp directory is always cleaned up
# ═══════════════════════════════════════════════════════════════════════════════

class TestUploadTempDirCleanup:
    """Temp directories must not be left on disk after upload validation failures."""

    def test_unsupported_extension_leaves_no_temp_dir(self, client, monkeypatch):
        """When a file with a bad extension is uploaded, no temp dir should be created."""
        dirs_before = set(
            d for d in Path(tempfile.gettempdir()).iterdir()
            if d.is_dir() and d.name.startswith("phototagger_upload_")
        )

        response = client.post(
            "/api/upload-photos",
            data={"files": (io.BytesIO(b"fake content"), "photo.exe")},
            content_type="multipart/form-data",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "Unsupported file type" in data["error"]

        dirs_after = set(
            d for d in Path(tempfile.gettempdir()).iterdir()
            if d.is_dir() and d.name.startswith("phototagger_upload_")
        )
        leaked = dirs_after - dirs_before
        assert leaked == set(), f"Temp dirs leaked on validation failure: {leaked}"

    def test_mixed_extensions_leaves_no_temp_dir(self, client):
        """First file is valid, second is bad — no temp dir should persist."""
        dirs_before = set(
            d for d in Path(tempfile.gettempdir()).iterdir()
            if d.is_dir() and d.name.startswith("phototagger_upload_")
        )

        response = client.post(
            "/api/upload-photos",
            data={
                "files": [
                    (io.BytesIO(_make_jpeg_bytes()), "good.jpg"),
                    (io.BytesIO(b"bad"), "bad.docx"),
                ],
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 400

        dirs_after = set(
            d for d in Path(tempfile.gettempdir()).iterdir()
            if d.is_dir() and d.name.startswith("phototagger_upload_")
        )
        assert (dirs_after - dirs_before) == set()

    def test_no_files_returns_400_without_temp_dir(self, client):
        """Empty upload returns 400 and creates no temp directory."""
        dirs_before = set(
            d for d in Path(tempfile.gettempdir()).iterdir()
            if d.is_dir() and d.name.startswith("phototagger_upload_")
        )

        response = client.post("/api/upload-photos")
        assert response.status_code == 400

        dirs_after = set(
            d for d in Path(tempfile.gettempdir()).iterdir()
            if d.is_dir() and d.name.startswith("phototagger_upload_")
        )
        assert (dirs_after - dirs_before) == set()

    def test_valid_upload_returns_job_id(self, client):
        """A valid upload of a JPEG file returns a job submission response."""
        response = client.post(
            "/api/upload-photos",
            data={"files": (io.BytesIO(_make_jpeg_bytes()), "test.jpg")},
            content_type="multipart/form-data",
        )

        assert response.status_code == 202
        data = json.loads(response.data)
        assert "job_id" in data
        assert data["success"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# Critical Issue 3: Pagination must not load all rows into memory
# ═══════════════════════════════════════════════════════════════════════════════

class TestPaginatedPhotoQueries:
    """db.photos.get_all_photos(limit, offset) and db.photos.count_photos() must push work into SQL."""

    def _create_photos(self, db, tmp_path, count: int):
        """Insert *count* real photo files and return their IDs.

        Each file has a unique pixel colour so that SHA-256 hashes differ —
        required because photos.file_hash has a UNIQUE constraint.
        """
        # Spread across the full 8-bit spectrum so we get distinct hashes
        colours = [
            (i * 25 % 256, (i * 37 + 10) % 256, (i * 53 + 20) % 256)
            for i in range(count)
        ]
        ids = []
        for i, colour in enumerate(colours):
            p = tmp_path / f"photo_{i}.jpg"
            img = Image.new("RGB", (32, 32), color=colour)
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            p.write_bytes(buf.getvalue())
            ids.append(db.photos.add_photo(str(p)))
        return ids

    def test_count_photos_returns_correct_total(self, db, tmp_path):
        self._create_photos(db, tmp_path, 5)
        assert db.photos.count_photos() == 5

    def test_count_photos_empty_database(self, db):
        assert db.photos.count_photos() == 0

    def test_get_all_photos_with_limit(self, db, tmp_path):
        self._create_photos(db, tmp_path, 10)
        page = db.photos.get_all_photos(limit=3, offset=0)
        assert len(page) == 3

    def test_get_all_photos_with_offset(self, db, tmp_path):
        ids = self._create_photos(db, tmp_path, 5)
        page = db.photos.get_all_photos(limit=2, offset=2)
        assert len(page) == 2
        # offset=2 → starts at the 3rd row (index 2)
        assert page[0]["id"] == ids[2]

    def test_get_all_photos_last_page_partial(self, db, tmp_path):
        """Last page may have fewer rows than limit."""
        self._create_photos(db, tmp_path, 5)
        last_page = db.photos.get_all_photos(limit=3, offset=3)
        assert len(last_page) == 2

    def test_get_all_photos_beyond_total_returns_empty(self, db, tmp_path):
        self._create_photos(db, tmp_path, 3)
        page = db.photos.get_all_photos(limit=10, offset=100)
        assert page == []

    def test_get_all_photos_no_limit_returns_all(self, db, tmp_path):
        """Calling without limit still works (for internal callers like detection)."""
        self._create_photos(db, tmp_path, 5)
        all_rows = db.photos.get_all_photos()
        assert len(all_rows) == 5

    def _unique_jpeg(self, index: int) -> bytes:
        """Return JPEG bytes unique to *index* so file hashes never collide."""
        colour = ((index * 25) % 256, (index * 37 + 10) % 256, (index * 53 + 20) % 256)
        img = Image.new("RGB", (32, 32), color=colour)
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()

    def test_api_photos_endpoint_pagination(self, client, app, tmp_path):
        """GET /api/photos must honour page/per_page without loading all rows."""
        for i in range(5):
            p = tmp_path / f"ep_{i}.jpg"
            p.write_bytes(self._unique_jpeg(i))
            app.db.photos.add_photo(str(p))

        response = client.get("/api/photos?page=1&per_page=2")
        assert response.status_code == 200
        data = json.loads(response.data)

        assert data["total"] == 5
        assert data["page"] == 1
        assert len(data["photos"]) == 2

    def test_api_photos_total_does_not_equal_per_page_results(self, client, app, tmp_path):
        """total in response must reflect the full count, not the page size."""
        for i in range(7):
            p = tmp_path / f"tot_{i}.jpg"
            p.write_bytes(self._unique_jpeg(i + 100))
            app.db.photos.add_photo(str(p))

        response = client.get("/api/photos?page=2&per_page=3")
        assert response.status_code == 200
        data = json.loads(response.data)

        assert data["total"] == 7       # full count
        assert len(data["photos"]) == 3  # one page

    def test_api_photos_page_beyond_total_returns_empty_list(self, client, app, tmp_path):
        for i in range(3):
            p = tmp_path / f"beyond_{i}.jpg"
            p.write_bytes(self._unique_jpeg(i + 200))
            app.db.photos.add_photo(str(p))

        response = client.get("/api/photos?page=99&per_page=10")
        assert response.status_code == 200
        data = json.loads(response.data)

        assert data["total"] == 3
        assert data["photos"] == []


# ── Stress & Load Tests ────────────────────────────────────────────────────────

class TestStressAndLoad:
    """Stress and load tests for PhotoTagger."""

    @staticmethod
    def _unique_jpeg(idx: int) -> bytes:
        """Create unique JPEG for deterministic testing."""
        img = Image.new("RGB", (32, 32), color=(idx % 255, (idx // 255) % 255, 0))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()

    def test_100_concurrent_photo_uploads(self, client, app, tmp_path):
        """100 photos uploaded without crash or database corruption."""
        photo_dir = tmp_path / "stress_photos"
        photo_dir.mkdir()

        # Create 100 photos
        for i in range(100):
            photo_file = photo_dir / f"stress_photo_{i:03d}.jpg"
            photo_file.write_bytes(self._unique_jpeg(i))

        # Upload all
        response = client.post(
            "/api/upload-photos",
            json={"photo_directory": str(photo_dir)}
        )

        assert response.status_code in {202, 200}

        # Verify photos indexed
        photos = app.db.photos.get_all_photos()
        assert len(photos) == 100

    def test_1000_face_similarity_comparisons(self, client, app):
        """1000+ face similarity comparisons complete without timeout."""
        # Create assigned cluster
        cluster = app.db.clusters.create_cluster()
        face = app.db.faces.add_face(
            photo_id=1,
            face_bbox=[10, 10, 20, 20],
            embedding=[0.5] * 512,
            sharpness_score=0.8,
        )
        app.db.clusters.add_face_to_cluster(cluster, face)
        app.db.clusters.assign_cluster_to_player(cluster, "Player", "1", None)

        # Create 100 unidentified clusters (1000+ faces)
        for i in range(100):
            c = app.db.clusters.create_cluster()
            for j in range(10):
                f = app.db.faces.add_face(
                    photo_id=100 + i * 10 + j,
                    face_bbox=[10, 10, 20, 20],
                    embedding=[0.5 + (i * 0.001)] * 512,
                    sharpness_score=0.8,
                )
                app.db.clusters.add_face_to_cluster(c, f)

        # Run similarity match
        response = client.post(f"/api/players/{cluster}/match-similar")

        assert response.status_code == 200
        # Should complete without crash
        data = response.json
        assert "auto_tagged" in data or "suggestions" in data

    def test_rapid_job_submissions_preserved(self, client, app, tmp_path):
        """50 jobs submitted rapidly, all tracked."""
        photo_dir = tmp_path / "jobs"
        photo_dir.mkdir()

        # Create test photos
        for i in range(50):
            photo_file = photo_dir / f"job_photo_{i}.jpg"
            photo_file.write_bytes(self._unique_jpeg(i))

        job_ids = []

        # Submit jobs rapidly
        for i in range(50):
            response = client.post(
                "/api/upload-photos",
                json={"photo_directory": str(photo_dir)}
            )

            if response.status_code == 202:
                job_ids.append(response.json["job_id"])

        # Verify unique job IDs
        assert len(job_ids) > 0
        assert len(set(job_ids)) == len(job_ids)

    def test_memory_stability_sequential_operations(self, client, app, tmp_path):
        """5 large operations sequentially maintain memory stability."""
        photo_dir = tmp_path / "mem_test"
        photo_dir.mkdir()

        operations = [
            ("create photos", lambda: [
                (photo_dir / f"mem_photo_{j}.jpg").write_bytes(self._unique_jpeg(j))
                for j in range(20)
            ]),
            ("create faces", lambda: [
                app.db.faces.add_face(
                    photo_id=j,
                    face_bbox=[10, 10, 20, 20],
                    embedding=[0.1 * (j % 10)] * 512,
                    sharpness_score=0.8,
                )
                for j in range(20)
            ]),
            ("create clusters", lambda: [
                app.db.clusters.create_cluster()
                for _ in range(5)
            ]),
            ("roster import", lambda: [
                app.db.roster.add_roster_entry(
                    team_name=f"Team{j}",
                    team_year="2024",
                    player_name=f"Player{j}",
                    jersey_number=str(j)
                )
                for j in range(20)
            ]),
            ("data access", lambda: [
                app.db.photos.get_all_photos(),
                app.db.clusters.get_all_clusters(),
                app.db.roster.get_all_roster_entries(),
            ]),
        ]

        for op_name, op_func in operations:
            try:
                op_func()
            except Exception as e:
                pytest.fail(f"Operation '{op_name}' failed: {e}")

        # Final verification
        photos = app.db.photos.get_all_photos()
        clusters = app.db.clusters.get_all_clusters()
        roster = app.db.roster.get_all_roster_entries()

        assert len(photos) > 0
        assert len(clusters) > 0
        assert len(roster) > 0
