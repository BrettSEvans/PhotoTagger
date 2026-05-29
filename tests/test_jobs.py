import json
import time

from src.api import create_app
from src.db import Database


def wait_for_job(db, job_id: int, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = db.get_processing_job(job_id)
        if job and job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for job {job_id}")


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


def test_crawl_endpoint_returns_job_and_completes(tmp_path):
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    client = app.test_client()
    (tmp_path / "one.jpg").write_bytes(b"one")

    response = client.post("/api/crawl", json={"photo_dir": str(tmp_path)})

    assert response.status_code == 202
    data = json.loads(response.data)
    assert data["success"] is True
    assert data["job_id"] > 0

    job = wait_for_job(app.db, data["job_id"])
    assert job["type"] == "crawl"
    assert job["status"] == "succeeded"
    assert job["progress"] == 100
    assert job["result"]["photos_found"] == 1


def test_process_ocr_endpoint_returns_job(monkeypatch):
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    client = app.test_client()

    monkeypatch.setattr(app.ocr_engine, "process_batch", lambda photo_ids=None: {"photos_processed": 0})

    response = client.post("/api/process-ocr", json={"photo_ids": [1, 2]})

    assert response.status_code == 202
    data = json.loads(response.data)
    job = wait_for_job(app.db, data["job_id"])
    assert job["type"] == "process_ocr"
    assert job["status"] == "succeeded"
    assert job["result"] == {"photos_processed": 0}


def test_detect_faces_endpoint_returns_job(monkeypatch, tmp_path):
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    client = app.test_client()
    photo_file = tmp_path / "one.jpg"
    photo_file.write_bytes(b"one")
    photo_id = app.db.add_photo(str(photo_file))

    class FakeDetector:
        def detect_faces(self, _file_path):
            return [{"embedding": [0.1] * 384, "bbox": [1, 2, 3, 4], "confidence": 0.9}]

    monkeypatch.setattr("src.face_detector.FaceDetector", lambda: FakeDetector())

    response = client.post("/api/detect-faces", json={"photo_ids": [photo_id]})

    assert response.status_code == 202
    data = json.loads(response.data)
    job = wait_for_job(app.db, data["job_id"])
    assert job["type"] == "detect_faces"
    assert job["status"] == "succeeded"
    assert job["result"]["faces_detected"] == 1


def test_cluster_players_endpoint_returns_job():
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.post("/api/cluster-players", json={"threshold": 0.4})

    assert response.status_code == 202
    data = json.loads(response.data)
    job = wait_for_job(app.db, data["job_id"])
    assert job["type"] == "cluster_players"
    assert job["status"] == "succeeded"
    assert job["result"]["clusters_created"] == 0
