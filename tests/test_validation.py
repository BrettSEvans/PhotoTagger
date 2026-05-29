import json

from src.api import create_app


def test_search_invalid_min_confidence_returns_400():
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.get("/api/search?jersey=16&min_confidence=bad")

    assert response.status_code == 400
    assert json.loads(response.data)["error"] == "min_confidence must be a number"


def test_photos_invalid_page_returns_400():
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.get("/api/photos?page=abc")

    assert response.status_code == 400
    assert json.loads(response.data)["error"] == "page must be an integer"


def test_cluster_invalid_threshold_returns_400():
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.post("/api/cluster-players", json={"threshold": "not-a-number"})

    assert response.status_code == 400
    assert json.loads(response.data)["error"] == "threshold must be a number"


def test_crawl_empty_photo_dir_returns_400():
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.post("/api/crawl", json={"photo_dir": ""})

    assert response.status_code == 400
    assert json.loads(response.data)["error"] == "photo_dir is required"


def test_crawl_rejects_git_metadata_directory():
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.post("/api/crawl", json={"photo_dir": ".git"})

    assert response.status_code == 400
    assert json.loads(response.data)["error"] == "photo_dir is not an allowed photo directory"


def test_local_agent_token_required_for_file_backed_endpoints(monkeypatch, tmp_path):
    monkeypatch.setenv("PHOTOTAGGER_MODE", "local-agent")
    monkeypatch.setenv("PHOTOTAGGER_AGENT_TOKEN", "secret-token")
    monkeypatch.setenv("PHOTOTAGGER_ALLOWED_PHOTO_ROOTS", str(tmp_path))
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.post("/api/crawl", json={"photo_dir": str(tmp_path)})

    assert response.status_code == 401
    assert json.loads(response.data)["error"] == "local agent token required"

    authed = client.post(
        "/api/crawl",
        json={"photo_dir": str(tmp_path)},
        headers={"X-PhotoTagger-Agent-Token": "secret-token"},
    )
    assert authed.status_code == 202


def test_allowed_photo_roots_reject_outside_paths(monkeypatch, tmp_path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    monkeypatch.setenv("PHOTOTAGGER_ALLOWED_PHOTO_ROOTS", str(allowed))
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.post("/api/crawl", json={"photo_dir": str(outside)})

    assert response.status_code == 400
    assert json.loads(response.data)["error"] == "photo_dir is not an allowed photo directory"
