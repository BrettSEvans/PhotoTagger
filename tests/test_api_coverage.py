"""
Tests for API endpoints that had zero coverage before this refactor branch.

Covers:
- GET  /api/app-config
- GET  /api/detection-status
- POST /api/data/reset
- GET  /api/processing-summary
- GET  /api/confirmed-photos
- GET  /api/review-photos
- GET  /api/image/<photo_id>
- GET  /api/batches
- GET  /api/batches/<id>
- PUT  /api/batches/<id>
- DELETE /api/batches/<id>
- POST /api/roster/infer
- POST /api/roster/infer-url (mocked)
- POST /api/upload-photos  (additional edge cases)
"""

import io
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image

from src.api import create_app
from src.db import Database


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_jpeg_bytes(color: str = "red") -> bytes:
    img = Image.new("RGB", (32, 32), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def wait_for_job(db: Database, job_id: int, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = db.get_processing_job(job_id)
        if job and job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for job {job_id}")


@pytest.fixture
def app():
    application = create_app(db_path=":memory:")
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


# ═══════════════════════════════════════════════════════════════════════════════
# /api/app-config
# ═══════════════════════════════════════════════════════════════════════════════

def test_app_config_returns_mode(client):
    resp = client.get("/api/app-config")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "mode" in data
    assert "requires_agent_token" in data


def test_app_config_no_auth_required(client):
    """app-config must be reachable without an agent token (used on first load)."""
    resp = client.get("/api/app-config")
    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# /api/detection-status
# ═══════════════════════════════════════════════════════════════════════════════

def test_detection_status_empty_db(client):
    resp = client.get("/api/detection-status")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["face_count"] == 0
    assert data["cluster_count"] == 0


def test_detection_status_returns_correct_counts(client, app, tmp_path):
    # Add a photo + face + cluster so counts > 0
    img = tmp_path / "det.jpg"
    img.write_bytes(_make_jpeg_bytes())
    photo_id = app.db.add_photo(str(img))
    app.db.add_face(photo_id=photo_id, embedding=[0.1] * 512, bbox=[0, 0, 10, 10], confidence=0.9)
    app.db.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=None)

    resp = client.get("/api/detection-status")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["face_count"] == 1
    assert data["cluster_count"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# /api/data/reset
# ═══════════════════════════════════════════════════════════════════════════════

def test_data_reset_requires_confirm(client):
    resp = client.post("/api/data/reset", json={})
    assert resp.status_code == 400
    assert "confirm" in json.loads(resp.data)["error"]


def test_data_reset_requires_confirm_true(client):
    resp = client.post("/api/data/reset", json={"confirm": False})
    assert resp.status_code == 400


def test_data_reset_clears_photos(client, app, tmp_path):
    img = tmp_path / "to_delete.jpg"
    img.write_bytes(_make_jpeg_bytes())
    app.db.add_photo(str(img))
    assert app.db.count_photos() == 1

    resp = client.post("/api/data/reset", json={"confirm": True})
    assert resp.status_code == 200
    assert json.loads(resp.data)["success"] is True
    assert app.db.count_photos() == 0


# ═══════════════════════════════════════════════════════════════════════════════
# /api/processing-summary
# ═══════════════════════════════════════════════════════════════════════════════

def test_processing_summary_empty_db(client):
    resp = client.get("/api/processing-summary")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "total_photos" in data
    assert data["total_photos"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# /api/confirmed-photos and /api/review-photos
# ═══════════════════════════════════════════════════════════════════════════════

def test_confirmed_photos_empty(client):
    resp = client.get("/api/confirmed-photos")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["photos"] == []


def test_review_photos_empty(client):
    resp = client.get("/api/review-photos")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["photos"] == []


def test_confirmed_photos_rejects_non_integer_limit(client):
    resp = client.get("/api/confirmed-photos?limit=abc")
    assert resp.status_code == 400


def test_review_photos_rejects_non_integer_offset(client):
    resp = client.get("/api/review-photos?offset=xyz")
    assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# /api/image/<photo_id>
# ═══════════════════════════════════════════════════════════════════════════════

def test_image_404_for_missing_photo(client):
    resp = client.get("/api/image/99999")
    assert resp.status_code == 404


def test_image_404_when_file_missing_from_disk(client, app, tmp_path):
    img = tmp_path / "gone.jpg"
    img.write_bytes(_make_jpeg_bytes())
    photo_id = app.db.add_photo(str(img))
    img.unlink()  # delete the actual file

    resp = client.get(f"/api/image/{photo_id}")
    assert resp.status_code == 404


def test_image_serves_jpeg(client, app, tmp_path):
    img = tmp_path / "real.jpg"
    img.write_bytes(_make_jpeg_bytes("green"))
    photo_id = app.db.add_photo(str(img))

    resp = client.get(f"/api/image/{photo_id}")
    assert resp.status_code == 200
    assert "image" in resp.content_type


# ═══════════════════════════════════════════════════════════════════════════════
# /api/batches — list, get, update, delete
# ═══════════════════════════════════════════════════════════════════════════════

def test_list_batches_empty(client):
    resp = client.get("/api/batches")
    assert resp.status_code == 200
    assert json.loads(resp.data)["batches"] == []


def test_list_batches_returns_created_batch(client, app, tmp_path):
    app.db.create_batch(source_folder=str(tmp_path), team_name="Team A", team_year=2026)
    resp = client.get("/api/batches")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert len(data["batches"]) == 1
    assert data["batches"][0]["team_name"] == "Team A"


def test_get_batch_404_for_missing(client):
    resp = client.get("/api/batches/99999")
    assert resp.status_code == 404


def test_get_batch_returns_batch_and_photos(client, app, tmp_path):
    batch_id = app.db.create_batch(source_folder=str(tmp_path))
    img = tmp_path / "b.jpg"
    img.write_bytes(_make_jpeg_bytes())
    app.db.add_photo(str(img), batch_id=batch_id)

    resp = client.get(f"/api/batches/{batch_id}")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["batch"]["id"] == batch_id
    assert len(data["photos"]) == 1


def test_update_batch_team_name(client, app, tmp_path):
    batch_id = app.db.create_batch(source_folder=str(tmp_path), team_name="Old Name")
    resp = client.put(f"/api/batches/{batch_id}", json={"team_name": "New Name"})
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["batch"]["team_name"] == "New Name"


def test_delete_batch_unpins_photos(client, app, tmp_path):
    batch_id = app.db.create_batch(source_folder=str(tmp_path))
    img = tmp_path / "del.jpg"
    img.write_bytes(_make_jpeg_bytes())
    app.db.add_photo(str(img), batch_id=batch_id)

    resp = client.delete(f"/api/batches/{batch_id}")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["affected_photos"] == 1

    # Batch gone, photo still in DB but batch_id is NULL
    assert app.db.get_batch(batch_id) is None
    photos = app.db.get_all_photos()
    assert all(p.get("batch_id") is None for p in photos)


# ═══════════════════════════════════════════════════════════════════════════════
# /api/roster/infer
# ═══════════════════════════════════════════════════════════════════════════════

def test_roster_infer_returns_team_and_year(client):
    resp = client.post("/api/roster/infer", json={"filename": "Carleton CUT 2026.csv"})
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "team_name" in data
    assert "team_year" in data


def test_roster_infer_requires_filename(client):
    resp = client.post("/api/roster/infer", json={})
    assert resp.status_code == 400
    assert "filename" in json.loads(resp.data)["error"]


# ═══════════════════════════════════════════════════════════════════════════════
# /api/roster/infer-url (external HTTP mocked)
# ═══════════════════════════════════════════════════════════════════════════════

def test_roster_infer_url_requires_url(client):
    resp = client.post("/api/roster/infer-url", json={})
    assert resp.status_code == 400
    assert "url" in json.loads(resp.data)["error"]


def test_roster_infer_url_returns_gracefully_on_fetch_failure(client):
    """If the URL fetch fails, the endpoint should return null team/year, not 500."""
    with patch("requests.get", side_effect=Exception("network error")):
        resp = client.post("/api/roster/infer-url", json={"url": "https://example.com/roster"})
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["team_name"] is None
    assert data["team_year"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# /api/upload-photos — additional edge cases
# ═══════════════════════════════════════════════════════════════════════════════

def test_upload_photos_rejects_txt_file(client):
    resp = client.post(
        "/api/upload-photos",
        data={"files": (io.BytesIO(b"not an image"), "notes.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "Unsupported" in json.loads(resp.data)["error"]


def test_upload_photos_accepts_png(client):
    img = Image.new("RGB", (10, 10), "blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    resp = client.post(
        "/api/upload-photos",
        data={"files": (buf, "shot.png")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 202


def test_upload_photos_no_files_key_returns_400(client):
    resp = client.post("/api/upload-photos", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "No files" in json.loads(resp.data)["error"]


def test_upload_photos_empty_filename_returns_400(client):
    resp = client.post(
        "/api/upload-photos",
        data={"files": (io.BytesIO(b""), "")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
