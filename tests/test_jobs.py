import json

from src.api import create_app
from src.db import Database


def test_processing_jobs_table_exists():
    db = Database(":memory:")
    db.init_schema()
    try:
        cursor = db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='processing_jobs'")
        assert cursor.fetchone() is not None
    finally:
        db.close()


def test_create_and_update_processing_job():
    db = Database(":memory:")
    db.init_schema()
    try:
        job_id = db.create_processing_job("crawl", {"photo_dir": "/tmp/photos"})
        job = db.get_processing_job(job_id)

        assert job is not None
        assert job["type"] == "crawl"
        assert job["status"] == "queued"
        assert job["progress"] == 0
        assert job["payload"] == {"photo_dir": "/tmp/photos"}

        db.update_processing_job(job_id, status="running", progress=25)
        running = db.get_processing_job(job_id)
        assert running["status"] == "running"
        assert running["progress"] == 25

        db.update_processing_job(job_id, status="succeeded", progress=100, result={"photos_found": 2})
        completed = db.get_processing_job(job_id)
        assert completed["status"] == "succeeded"
        assert completed["progress"] == 100
        assert completed["result"] == {"photos_found": 2}
        assert completed["finished_at"] is not None
    finally:
        db.close()


def test_get_job_endpoint_returns_status():
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    client = app.test_client()
    job_id = app.db.create_processing_job("detect_faces", {"photo_ids": [1, 2]})
    app.db.update_processing_job(job_id, status="failed", progress=40, error="model unavailable")

    response = client.get(f"/api/jobs/{job_id}")

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["job"]["id"] == job_id
    assert data["job"]["type"] == "detect_faces"
    assert data["job"]["status"] == "failed"
    assert data["job"]["error"] == "model unavailable"


def test_get_job_endpoint_404_for_missing_job():
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.get("/api/jobs/9999")

    assert response.status_code == 404
    data = json.loads(response.data)
    assert data["error"] == "Job not found"
