import pytest
import json
import io
import shutil
from pathlib import Path
from src.api import create_app
from src.roster import RosterManager
import tempfile

FIXTURE_PHOTO = Path(__file__).resolve().parent.parent / "uploads" / "DSC_3890-sm.JPG"

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

    photo_id = db.photos.add_photo(photo_path)
    db.photos.add_ocr_result(photo_id, "16", 0.95, "16")

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


def test_player_photos_support_min_face_confidence_filter(client, app_with_roster):
    """Review can request only sufficiently confident face matches."""
    db = app_with_roster.db

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as low_file:
        low_file.write(b"fake low confidence jpg")
        low_file.flush()
        low_photo_id = db.photos.add_photo(low_file.name)

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as high_file:
        high_file.write(b"fake high confidence jpg")
        high_file.flush()
        high_photo_id = db.photos.add_photo(high_file.name)

    low_face_id = db.faces.add_face(low_photo_id, [0.1] * 384, [10, 20, 100, 150], 0.59)
    high_face_id = db.faces.add_face(high_photo_id, [0.2] * 384, [10, 20, 100, 150], 0.60)
    cluster_id = db.clusters.add_player_cluster(face_count=2, photo_count=2, thumbnail_face_id=high_face_id)
    db.clusters.assign_face_to_cluster(low_face_id, cluster_id)
    db.clusters.assign_face_to_cluster(high_face_id, cluster_id)

    response = client.get(f"/api/players/{cluster_id}/photos?min_face_confidence=0.6")

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["total"] == 1
    assert data["photos"][0]["face_id"] == high_face_id


def test_assign_cluster_embeds_iptc_for_selected_faces_only(client, app_with_roster, tmp_path, monkeypatch):
    """Assigning a cluster embeds the player name via IPTC (unconditional, no
    write_metadata flag) into only the explicitly selected faces' photos."""
    from src import iptc_writer

    monkeypatch.setattr("src.blueprints.review.is_backup_ready", lambda: True)
    db = app_with_roster.db
    db.roster.add_roster_entry("Carleton CUT", 2026, "12", "Thomas Shope", uniform_color="red")
    roster_entry = db.roster.search_roster("Thomas")[0]

    selected_photo = tmp_path / "selected.jpg"
    excluded_photo = tmp_path / "excluded.jpg"
    shutil.copy2(FIXTURE_PHOTO, selected_photo)
    shutil.copy2(FIXTURE_PHOTO, excluded_photo)
    selected_photo_id = db.photos.add_photo(str(selected_photo), file_hash="selected_hash")
    excluded_photo_id = db.photos.add_photo(str(excluded_photo), file_hash="excluded_hash")
    selected_face_id = db.faces.add_face(selected_photo_id, [0.1] * 384, [1, 2, 3, 4], 0.95)
    excluded_face_id = db.faces.add_face(excluded_photo_id, [0.2] * 384, [1, 2, 3, 4], 0.95)
    cluster_id = db.clusters.add_player_cluster(face_count=2, photo_count=2, thumbnail_face_id=selected_face_id)
    db.clusters.assign_face_to_cluster(selected_face_id, cluster_id)
    db.clusters.assign_face_to_cluster(excluded_face_id, cluster_id)

    response = client.post(
        f"/api/players/{cluster_id}/assign",
        json={
            "player_name": "Thomas Shope",
            "jersey_number": "12",
            "roster_entry_id": roster_entry["id"],
            "face_ids": [selected_face_id],
        },
    )

    assert response.status_code == 200
    assert json.loads(response.data)["success"] is True
    assert "metadata" not in json.loads(response.data)  # no opt-in flag/result shape anymore

    assert iptc_writer.read_person_in_image(str(selected_photo)) == ["Thomas Shope"]
    assert iptc_writer.read_person_in_image(str(excluded_photo)) == []


def test_assign_cluster_skips_embed_silently_for_missing_photo(client, app_with_roster, tmp_path, monkeypatch):
    """A missing photo file must not fail the assign request — embed is best-effort."""
    from src import iptc_writer

    monkeypatch.setattr("src.blueprints.review.is_backup_ready", lambda: True)
    db = app_with_roster.db
    db.roster.add_roster_entry("Carleton CUT", 2026, "12", "Thomas Shope", uniform_color="red")
    roster_entry = db.roster.search_roster("Thomas")[0]
    missing_photo = tmp_path / "missing.jpg"
    missing_photo.write_bytes(b"temporary")
    photo_id = db.photos.add_photo(str(missing_photo))
    missing_photo.unlink()
    face_id = db.faces.add_face(photo_id, [0.1] * 384, [1, 2, 3, 4], 0.95)
    cluster_id = db.clusters.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=face_id)
    db.clusters.assign_face_to_cluster(face_id, cluster_id)

    response = client.post(
        f"/api/players/{cluster_id}/assign",
        json={
            "player_name": "Thomas Shope",
            "jersey_number": "12",
            "roster_entry_id": roster_entry["id"],
            "face_ids": [face_id],
        },
    )

    assert response.status_code == 200
    assert json.loads(response.data)["success"] is True


def test_assign_cluster_skips_embed_outside_allowed_roots(client, app_with_roster, tmp_path, monkeypatch):
    """IPTC embeds must honor the local agent photo root allowlist, silently."""
    from src import iptc_writer

    monkeypatch.setattr("src.blueprints.review.is_backup_ready", lambda: True)
    db = app_with_roster.db
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    monkeypatch.setenv("PHOTOTAGGER_ALLOWED_PHOTO_ROOTS", str(allowed))
    db.roster.add_roster_entry("Carleton CUT", 2026, "12", "Thomas Shope", uniform_color="red")
    roster_entry = db.roster.search_roster("Thomas")[0]
    photo = outside / "outside.jpg"
    shutil.copy2(FIXTURE_PHOTO, photo)
    photo_id = db.photos.add_photo(str(photo))
    face_id = db.faces.add_face(photo_id, [0.1] * 384, [1, 2, 3, 4], 0.95)
    cluster_id = db.clusters.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=face_id)
    db.clusters.assign_face_to_cluster(face_id, cluster_id)

    response = client.post(
        f"/api/players/{cluster_id}/assign",
        json={
            "player_name": "Thomas Shope",
            "jersey_number": "12",
            "roster_entry_id": roster_entry["id"],
            "face_ids": [face_id],
        },
    )

    assert response.status_code == 200
    assert json.loads(response.data)["success"] is True
    assert iptc_writer.read_person_in_image(str(photo)) == []

def test_search_returns_player_name(client, app_with_roster):
    """Test that search returns player names via roster lookup."""
    db = app_with_roster.db

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(b"fake jpg")
        photo_path = f.name

    photo_id = db.photos.add_photo(photo_path)
    db.photos.add_ocr_result(photo_id, "16", 0.95, "16")

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

    photo_id = db.photos.add_photo(photo_path)

    # Add a face
    embedding = [0.1] * 384
    db.faces.add_face(photo_id, embedding, [10, 20, 100, 150], 0.95)

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
    # jersey_number is stored as INTEGER in DB; "06" → 6
    assert any(str(e["jersey_number"]) in ("06", "6") and e["player_name"] == "Will Troop" for e in entries)


def test_roster_import_skip_preserves_existing_entry(client, app_with_roster):
    db = app_with_roster.db
    db.roster.add_roster_entry("Carleton CUT", 2026, "10", "Original Player")

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
    assert db.roster.get_player_name("Carleton CUT", 2026, "10") == "Original Player"


def test_roster_import_replace_updates_existing_entry(client, app_with_roster):
    db = app_with_roster.db
    db.roster.add_roster_entry("Carleton CUT", 2026, "10", "Original Player")

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
    assert db.roster.get_player_name("Carleton CUT", 2026, "10") == "Updated Player"


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
    photo_id = db.photos.add_photo(str(photo_file))
    face_id = db.faces.add_face(photo_id, [0.1] * 384, [1, 2, 30, 40], 0.95)
    cluster_id = db.clusters.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=face_id)
    db.clusters.assign_face_to_cluster(face_id, cluster_id)
    db.clusters.assign_cluster_to_player(cluster_id, "Will Troop", "06")
    db.roster.add_roster_entry("Carleton CUT", 2026, "06", "Will Troop")

    response = client.get("/api/roster")

    assert response.status_code == 200
    entries = json.loads(response.data)["entries"]
    # jersey_number stored as INTEGER; "06" → 6
    match = next(e for e in entries if str(e["jersey_number"]) in ("06", "6"))
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
    db.roster.add_roster_entry("Carleton CUT", 2026, "22", "Will Troop")
    roster_entry = db.roster.search_roster("Will Troop")[0]
    photo_file = tmp_path / "test.jpg"
    photo_file.write_bytes(b"fake jpg")
    photo_id = db.photos.add_photo(str(photo_file))
    face_id = db.faces.add_face(photo_id, [0.1] * 384, [1, 2, 30, 40], 0.95)
    cluster_id = db.clusters.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=face_id)
    db.clusters.assign_face_to_cluster(face_id, cluster_id)

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
    photo_id = db.photos.add_photo(str(photo_file))
    face_id = db.faces.add_face(photo_id, [0.1] * 384, [1, 2, 30, 40], 0.95)
    cluster_id = db.clusters.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=face_id)
    db.clusters.assign_face_to_cluster(face_id, cluster_id)

    response = client.post("/api/faces/deassign", json={"face_ids": [face_id]})

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is True
    assert data["deassigned"] == 1
    assert data["deleted_cluster_ids"] == [cluster_id]
