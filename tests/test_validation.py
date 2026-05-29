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
