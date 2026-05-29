import pytest
import json
import time
from pathlib import Path
from src.api import create_app, get_server_bind, should_enable_debug
from src.db import Database


def wait_for_job(db, job_id: int, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = db.get_processing_job(job_id)
        if job and job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for job {job_id}")

@pytest.fixture
def app():
    """Create a Flask test app with in-memory database."""
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    return app

@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()

def test_api_initialization(app):
    """Verify API app initializes."""
    assert app is not None

def test_debug_mode_is_opt_in(monkeypatch):
    """Flask debug mode should not be enabled unless explicitly requested."""
    monkeypatch.delenv("PHOTOTAGGER_DEBUG", raising=False)
    assert should_enable_debug() is False

    monkeypatch.setenv("PHOTOTAGGER_DEBUG", "true")
    assert should_enable_debug() is True


def test_server_bind_uses_railway_port(monkeypatch):
    """Hosted mode should bind to Railway's PORT on all interfaces."""
    monkeypatch.setenv("PORT", "8123")
    monkeypatch.setenv("PHOTOTAGGER_MODE", "cloud-ui")

    assert get_server_bind() == ("0.0.0.0", 8123)

def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "ok"

def test_search_no_results(client):
    """Test search endpoint when no results found."""
    response = client.get("/api/search?jersey=23")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["results"] == []
    assert data["count"] == 0

def test_search_with_results(client, app):
    """Test search endpoint with actual results."""
    # Add a photo and OCR result to the database
    db = app.db

    # Create a dummy photo
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(b"fake jpg")
        photo_path = f.name

    photo_id = db.add_photo(photo_path)
    db.add_ocr_result(photo_id, "23", 0.95, "23 visible")

    # Search for jersey 23
    response = client.get("/api/search?jersey=23")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["count"] == 1
    assert data["results"][0]["jersey_number"] == "23"

def test_crawl_endpoint(client, tmp_path):
    """Test crawl endpoint."""
    # Create test photos
    for i in range(2):
        photo = tmp_path / f"photo{i}.jpg"
        photo.write_bytes(b"fake jpg")

    # Call crawl endpoint
    response = client.post("/api/crawl", json={"photo_dir": str(tmp_path)})
    assert response.status_code == 202
    data = json.loads(response.data)
    assert data["success"] is True
    assert data["job_id"] > 0
    job = wait_for_job(client.application.db, data["job_id"])
    assert job["status"] == "succeeded"
    assert job["result"]["photos_found"] == 2

def test_info_endpoint(client):
    """Test info endpoint."""
    response = client.get("/api/info")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "total_photos" in data
    assert data["total_photos"] == 0
