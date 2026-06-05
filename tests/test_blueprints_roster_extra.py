"""
Additional tests for src/blueprints/roster.py — covers the uncovered
error paths, validation branches, and the search/infer/import-url
endpoints that the base blueprint tests miss.
"""

import io
import json
from unittest.mock import patch

import pytest

from src.api import create_app


@pytest.fixture
def ctx():
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    yield app.test_client(), app.db


# ---------------------------------------------------------------------------
# GET /api/roster — exception path (lines 21-22)
# ---------------------------------------------------------------------------

def test_get_roster_error_path(ctx):
    client, db = ctx
    with patch.object(db.roster, "get_all_roster_entries", side_effect=RuntimeError("boom")):
        r = client.get("/api/roster")
    assert r.status_code in (500, 200)  # either handled or passes through


# ---------------------------------------------------------------------------
# PUT /api/game-context — validation paths
# ---------------------------------------------------------------------------

def test_put_game_context_teams_not_list(ctx):
    client, _ = ctx
    r = client.put("/api/game-context", json={"teams": "not_a_list"})
    assert r.status_code == 400


def test_put_game_context_missing_team_name(ctx):
    client, _ = ctx
    r = client.put("/api/game-context", json={
        "teams": [{"team_year": 2024, "uniform_color": "red"}]
    })
    assert r.status_code == 400


def test_put_game_context_invalid_year(ctx):
    client, _ = ctx
    r = client.put("/api/game-context", json={
        "teams": [{"team_name": "A", "team_year": "notanint", "uniform_color": "red"}]
    })
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/roster — validation paths (lines 77-78, 83-84, 92-93)
# ---------------------------------------------------------------------------

def test_add_roster_invalid_jersey_number(ctx):
    client, _ = ctx
    r = client.post("/api/roster", json={
        "team_name": "Team A",
        "player_name": "Alice",
        "jersey_number": "notanumber",
    })
    assert r.status_code == 400


def test_add_roster_invalid_team_year(ctx):
    client, _ = ctx
    r = client.post("/api/roster", json={
        "team_name": "Team A",
        "player_name": "Alice",
        "team_year": "nope",
    })
    assert r.status_code == 400


def test_add_roster_missing_player_name(ctx):
    client, _ = ctx
    r = client.post("/api/roster", json={"team_name": "Team A"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/roster/infer — covers lines 104-108
# ---------------------------------------------------------------------------

def test_infer_missing_filename(ctx):
    client, _ = ctx
    r = client.post("/api/roster/infer", json={})
    assert r.status_code == 400


def test_infer_with_filename(ctx):
    client, _ = ctx
    r = client.post("/api/roster/infer", json={"filename": "carleton_cut_2026.csv"})
    assert r.status_code == 200
    data = r.get_json()
    assert "team_name" in data
    assert "team_year" in data


# ---------------------------------------------------------------------------
# POST /api/roster/import — validation paths (lines 118-119, 123, 127)
# ---------------------------------------------------------------------------

def test_import_invalid_year(ctx):
    client, _ = ctx
    r = client.post("/api/roster/import", data={
        "team_name": "Team A",
        "team_year": "nope",
        "file": (io.BytesIO(b"Jersey,Name\n7,Alice\n"), "r.csv"),
    }, content_type="multipart/form-data")
    assert r.status_code == 400


def test_import_invalid_duplicate_policy(ctx):
    client, _ = ctx
    r = client.post("/api/roster/import", data={
        "team_name": "Team A",
        "team_year": "2024",
        "duplicate_policy": "invalidpolicy",
        "file": (io.BytesIO(b"Jersey,Name\n7,Alice\n"), "r.csv"),
    }, content_type="multipart/form-data")
    assert r.status_code == 400


def test_import_missing_file(ctx):
    client, _ = ctx
    r = client.post("/api/roster/import", data={
        "team_name": "Team A",
        "team_year": "2024",
    }, content_type="multipart/form-data")
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/roster/infer-url — covers lines 141-159
# ---------------------------------------------------------------------------

def test_infer_url_missing_url(ctx):
    client, _ = ctx
    r = client.post("/api/roster/infer-url", json={})
    assert r.status_code == 400


def test_infer_url_with_invalid_url(ctx):
    """Connecting to an invalid URL should return gracefully (not 500)."""
    client, _ = ctx
    # Mock requests.get to raise an exception
    with patch("src.blueprints.roster.requests.get", side_effect=Exception("no network")):
        r = client.post("/api/roster/infer-url", json={"url": "http://fake.invalid/roster"})
    assert r.status_code == 200  # error is handled gracefully
    data = r.get_json()
    assert data["team_name"] is None


def test_infer_url_success(ctx):
    """Successful URL fetch returns team/year."""
    client, _ = ctx
    from unittest.mock import MagicMock
    mock_resp = MagicMock()
    mock_resp.text = '<div class="profile_info"><h4>Carleton (CUT)</h4></div>'
    mock_resp.raise_for_status.return_value = None
    with patch("src.blueprints.roster.requests.get", return_value=mock_resp):
        r = client.post("/api/roster/infer-url", json={"url": "http://example.com/roster"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["team_name"] == "Carleton (CUT)"


# ---------------------------------------------------------------------------
# POST /api/roster/import-url — covers lines 162-189
# ---------------------------------------------------------------------------

def test_import_url_missing_url(ctx):
    client, _ = ctx
    r = client.post("/api/roster/import-url", json={})
    assert r.status_code == 400


def test_import_url_invalid_year(ctx):
    client, _ = ctx
    r = client.post("/api/roster/import-url", json={
        "url": "http://example.com",
        "team_year": "nope",
    })
    assert r.status_code == 400


def test_import_url_invalid_policy(ctx):
    client, _ = ctx
    r = client.post("/api/roster/import-url", json={
        "url": "http://example.com",
        "duplicate_policy": "invalid",
    })
    assert r.status_code == 400


def test_import_url_fetch_error(ctx):
    """When URL fetch fails, return error gracefully."""
    client, _ = ctx
    from src.roster_import import RosterImportError
    with patch("src.blueprints.roster.RosterImporter.fetch_url",
               side_effect=RosterImportError("no table found")):
        r = client.post("/api/roster/import-url", json={"url": "http://example.com"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# PUT /api/roster/<id> — validation paths (lines 220-221, 223, 225, 227)
# ---------------------------------------------------------------------------

def test_update_roster_invalid_jersey(ctx):
    client, db = ctx
    db.roster.add_roster_entry("Team A", 2024, "7", "Alice")
    entry = db.roster.get_all_roster_entries()[0]
    r = client.put(f"/api/roster/{entry['id']}", json={"jersey_number": "notanint"})
    assert r.status_code == 400


def test_update_roster_all_fields(ctx):
    client, db = ctx
    db.roster.add_roster_entry("Team A", 2024, "7", "Alice")
    entry = db.roster.get_all_roster_entries()[0]
    r = client.put(f"/api/roster/{entry['id']}", json={
        "player_name": "Alice Updated",
        "team_name": "Team B",
        "team_year": 2025,
        "uniform_color": "red",
    })
    assert r.status_code == 200


def test_update_roster_clear_jersey(ctx):
    client, db = ctx
    db.roster.add_roster_entry("Team A", 2024, "7", "Alice")
    entry = db.roster.get_all_roster_entries()[0]
    r = client.put(f"/api/roster/{entry['id']}", json={"jersey_number": None})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/roster/search — covers lines 239-250
# ---------------------------------------------------------------------------

def test_search_empty_query_returns_empty(ctx):
    client, _ = ctx
    r = client.get("/api/roster/search?q=")
    assert r.status_code == 200
    assert r.get_json()["results"] == []


def test_search_no_matches(ctx):
    client, _ = ctx
    r = client.get("/api/roster/search?q=zzznotfound")
    assert r.status_code == 200
    assert r.get_json()["results"] == []


def test_search_with_match(ctx):
    client, db = ctx
    db.roster.add_roster_entry("Team A", 2024, "7", "Alice Smith")
    r = client.get("/api/roster/search?q=Alice")
    assert r.status_code == 200
    results = r.get_json()["results"]
    assert any("Alice" in str(e.get("player_name", "")) for e in results)
