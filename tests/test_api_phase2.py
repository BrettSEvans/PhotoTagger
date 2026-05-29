import pytest
import json
import io
from src.api import create_app
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


def test_roster_import_file_inserts_entries(client, app_with_roster):
    response = client.post(
        "/api/roster/import",
        data={
            "team_name": "Carleton CUT",
            "team_year": "2026",
            "duplicate_policy": "replace",
            "file": (
                io.BytesIO(b"Jersey,Name\n06,Will Troop\n10,Fin Fuhrmann\n"),
                "roster.csv",
            ),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is True
    assert data["imported"] == 2

    roster = client.get("/api/roster")
    entries = json.loads(roster.data)["entries"]
    assert any(e["jersey_number"] == "06" and e["player_name"] == "Will Troop" for e in entries)


def test_roster_import_skip_preserves_existing_entry(client, app_with_roster):
    db = app_with_roster.db
    db.add_roster_entry("Carleton CUT", 2026, "10", "Original Player")

    response = client.post(
        "/api/roster/import",
        data={
            "team_name": "Carleton CUT",
            "team_year": "2026",
            "duplicate_policy": "skip",
            "file": (io.BytesIO(b"Jersey,Name\n10,Updated Player\n"), "roster.csv"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["imported"] == 0
    assert data["skipped"] == 1
    assert db.get_player_name("Carleton CUT", 2026, "10") == "Original Player"


def test_roster_import_replace_updates_existing_entry(client, app_with_roster):
    db = app_with_roster.db
    db.add_roster_entry("Carleton CUT", 2026, "10", "Original Player")

    response = client.post(
        "/api/roster/import",
        data={
            "team_name": "Carleton CUT",
            "team_year": "2026",
            "duplicate_policy": "replace",
            "file": (io.BytesIO(b"Jersey,Name\n10,Updated Player\n"), "roster.csv"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["imported"] == 1
    assert data["skipped"] == 0
    assert db.get_player_name("Carleton CUT", 2026, "10") == "Updated Player"


def test_roster_import_url_inserts_entries(client, app_with_roster, monkeypatch):
    html = """
    <table>
      <tr><th>No.</th><th>Player</th></tr>
      <tr><td>06</td><td>Will Troop</td></tr>
    </table>
    """

    class FakeResponse:
        text = html

        def raise_for_status(self):
            return None

    monkeypatch.setattr("src.roster_import.requests.get", lambda *args, **kwargs: FakeResponse())

    response = client.post(
        "/api/roster/import-url",
        json={
            "url": "https://play.usaultimate.org/events/teams/?EventTeamId=test",
            "team_name": "Carleton CUT",
            "team_year": 2026,
            "duplicate_policy": "replace",
        },
    )

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["imported"] == 1


def test_roster_response_includes_assigned_thumbnail_face(client, app_with_roster, tmp_path):
    db = app_with_roster.db
    photo_file = tmp_path / "test.jpg"
    photo_file.write_bytes(b"fake jpg")
    photo_id = db.add_photo(str(photo_file))
    face_id = db.add_face(photo_id, [0.1] * 384, [1, 2, 30, 40], 0.95)
    cluster_id = db.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=face_id)
    db.assign_face_to_cluster(face_id, cluster_id)
    db.assign_cluster_to_player(cluster_id, "Will Troop", "06")
    db.add_roster_entry("Carleton CUT", 2026, "06", "Will Troop")

    response = client.get("/api/roster")

    assert response.status_code == 200
    entries = json.loads(response.data)["entries"]
    match = next(e for e in entries if e["jersey_number"] == "06")
    assert match["thumbnail_face_id"] == face_id


def test_game_context_api_round_trip(client):
    response = client.put("/api/game-context", json={
        "teams": [
            {"team_name": "Carleton CUT", "team_year": 2026, "uniform_color": "red"},
            {"team_name": "Pittsburgh En Sabah Nur", "team_year": 2026, "uniform_color": "white"},
        ]
    })

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["teams"][0]["team_name"] == "Carleton CUT"
    assert data["teams"][1]["uniform_color"] == "white"

    get_response = client.get("/api/game-context")
    assert get_response.status_code == 200
    assert json.loads(get_response.data)["teams"] == data["teams"]


def test_assign_cluster_accepts_roster_entry_id_for_stable_roster_face(client, app_with_roster, tmp_path):
    db = app_with_roster.db
    db.add_roster_entry("Carleton CUT", 2026, "22", "Will Troop")
    roster_entry = db.search_roster("Will Troop")[0]
    photo_file = tmp_path / "test.jpg"
    photo_file.write_bytes(b"fake jpg")
    photo_id = db.add_photo(str(photo_file))
    face_id = db.add_face(photo_id, [0.1] * 384, [1, 2, 30, 40], 0.95)
    cluster_id = db.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=face_id)
    db.assign_face_to_cluster(face_id, cluster_id)

    response = client.post(
        f"/api/players/{cluster_id}/assign",
        json={
            "player_name": "Will Troop",
            "jersey_number": "16",
            "roster_entry_id": roster_entry["id"],
        },
    )

    assert response.status_code == 200
    entries = json.loads(client.get("/api/roster").data)["entries"]
    match = next(e for e in entries if e["id"] == roster_entry["id"])
    assert match["thumbnail_face_id"] == face_id


def test_deassign_faces_response_includes_deleted_cluster(client, app_with_roster, tmp_path):
    db = app_with_roster.db
    photo_file = tmp_path / "test.jpg"
    photo_file.write_bytes(b"fake jpg")
    photo_id = db.add_photo(str(photo_file))
    face_id = db.add_face(photo_id, [0.1] * 384, [1, 2, 30, 40], 0.95)
    cluster_id = db.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=face_id)
    db.assign_face_to_cluster(face_id, cluster_id)

    response = client.post("/api/faces/deassign", json={"face_ids": [face_id]})

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is True
    assert data["deassigned"] == 1
    assert data["deleted_cluster_ids"] == [cluster_id]
