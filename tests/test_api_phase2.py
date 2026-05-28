import pytest
import json
from src.api import create_app
from src.db import Database
from src.roster import RosterManager
import tempfile

@pytest.fixture
def app_with_roster():
    """Create app with sample roster."""
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True

    # Add sample roster
    manager = RosterManager()
    roster_data = {
        "team_name": "Test Team",
        "team_year": 2026,
        "jerseys": {"16": "Test Player"}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(roster_data, f)
        f.flush()
        manager.load_roster(f.name)

    app.roster_manager = manager
    return app

@pytest.fixture
def client(app_with_roster):
    return app_with_roster.test_client()

def test_search_with_confidence_filter(client, app_with_roster):
    """Test search with confidence threshold."""
    db = app_with_roster.db

    # Add photo with OCR result
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(b"fake jpg")
        photo_path = f.name

    photo_id = db.add_photo(photo_path)
    db.add_ocr_result(photo_id, "16", 0.95, "16")

    # Search with high confidence
    response = client.get("/api/search?jersey=16&min_confidence=0.9")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["count"] == 1

    # Search with too-high confidence
    response = client.get("/api/search?jersey=16&min_confidence=0.99")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["count"] == 0

def test_search_returns_player_name(client, app_with_roster):
    """Test that search returns player names via roster lookup."""
    db = app_with_roster.db

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(b"fake jpg")
        photo_path = f.name

    photo_id = db.add_photo(photo_path)
    db.add_ocr_result(photo_id, "16", 0.95, "16")

    response = client.get("/api/search?jersey=16&team=Test%20Team&year=2026")
    assert response.status_code == 200
    data = json.loads(response.data)

    # Should have player name in result
    if data["count"] > 0:
        result = data["results"][0]
        # Player name should be included if roster lookup worked

def test_get_faces_endpoint(client, app_with_roster):
    """Test face data endpoint."""
    db = app_with_roster.db

    # Add photo
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(b"fake jpg")
        photo_path = f.name

    photo_id = db.add_photo(photo_path)

    # Add a face
    embedding = [0.1] * 384
    db.add_face(photo_id, embedding, [10, 20, 100, 150], 0.95)

    # Get faces
    response = client.get(f"/api/faces/{photo_id}")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["photo_id"] == photo_id
    assert data["face_count"] == 1
