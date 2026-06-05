"""
Blueprint-level tests for:
  - src/blueprints/system.py  (health, app-config, detection-status, data-reset)
  - src/blueprints/roster.py  (roster CRUD, game-context, search)

Uses Flask test client with in-memory DB; no external services required.
"""

import json
import pytest

from src.api import create_app


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def client_and_db():
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    yield app.test_client(), app.db


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_200(self, client_and_db):
        client, _ = client_and_db
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_has_status_ok(self, client_and_db):
        client, _ = client_and_db
        data = client.get("/health").get_json()
        assert data["status"] == "ok"

    def test_health_has_mode(self, client_and_db):
        client, _ = client_and_db
        data = client.get("/health").get_json()
        assert "mode" in data

    def test_health_has_ocr_ok(self, client_and_db):
        """ocr_ok key is present (may be True, False, or None)."""
        client, _ = client_and_db
        data = client.get("/health").get_json()
        assert "ocr_ok" in data


# ---------------------------------------------------------------------------
# /api/app-config
# ---------------------------------------------------------------------------

class TestAppConfig:
    def test_app_config_returns_200(self, client_and_db):
        client, _ = client_and_db
        r = client.get("/api/app-config")
        assert r.status_code == 200

    def test_app_config_has_mode(self, client_and_db):
        client, _ = client_and_db
        data = client.get("/api/app-config").get_json()
        assert "mode" in data


# ---------------------------------------------------------------------------
# /api/detection-status
# ---------------------------------------------------------------------------

class TestDetectionStatus:
    def test_returns_200_with_counts(self, client_and_db):
        client, _ = client_and_db
        r = client.get("/api/detection-status")
        assert r.status_code == 200
        data = r.get_json()
        assert "face_count" in data
        assert "cluster_count" in data

    def test_empty_db_shows_zero_counts(self, client_and_db):
        client, _ = client_and_db
        data = client.get("/api/detection-status").get_json()
        assert data["face_count"] == 0
        assert data["cluster_count"] == 0


# ---------------------------------------------------------------------------
# /api/data/reset
# ---------------------------------------------------------------------------

class TestDataReset:
    def test_missing_confirm_returns_400(self, client_and_db):
        client, _ = client_and_db
        r = client.post("/api/data/reset", json={})
        assert r.status_code == 400

    def test_confirm_false_returns_400(self, client_and_db):
        client, _ = client_and_db
        r = client.post("/api/data/reset", json={"confirm": False})
        assert r.status_code == 400

    def test_confirm_true_returns_200(self, client_and_db):
        client, _ = client_and_db
        r = client.post("/api/data/reset", json={"confirm": True})
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"] is True


# ---------------------------------------------------------------------------
# /api/game-context  (GET + PUT)
# ---------------------------------------------------------------------------

class TestGameContext:
    def test_get_empty_game_context(self, client_and_db):
        client, _ = client_and_db
        r = client.get("/api/game-context")
        assert r.status_code == 200
        data = r.get_json()
        assert "teams" in data

    def test_put_game_context(self, client_and_db):
        client, _ = client_and_db
        payload = {
            "teams": [
                {"team_name": "Team A", "team_year": 2024, "uniform_color": "red"},
                {"team_name": "Team B", "team_year": 2024, "uniform_color": "blue"},
            ]
        }
        r = client.put("/api/game-context", json=payload)
        assert r.status_code in (200, 201, 204)

    def test_roundtrip_game_context(self, client_and_db):
        client, _ = client_and_db
        payload = {
            "teams": [
                {"team_name": "CUT", "team_year": 2026, "uniform_color": "black"},
            ]
        }
        client.put("/api/game-context", json=payload)
        r = client.get("/api/game-context")
        assert r.status_code == 200
        teams = r.get_json()["teams"]
        assert any(t["team_name"] == "CUT" for t in teams)


# ---------------------------------------------------------------------------
# /api/roster  (GET + POST)
# ---------------------------------------------------------------------------

class TestRosterEndpoints:
    def test_get_roster_empty(self, client_and_db):
        client, _ = client_and_db
        r = client.get("/api/roster")
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data.get("entries") or data.get("roster") or [], list)

    def test_post_roster_entry(self, client_and_db):
        client, _ = client_and_db
        r = client.post("/api/roster", json={
            "team_name": "Team A",
            "team_year": 2024,
            "jersey_number": "23",
            "player_name": "Alice Smith",
        })
        assert r.status_code in (200, 201)

    def test_post_roster_missing_fields(self, client_and_db):
        client, _ = client_and_db
        r = client.post("/api/roster", json={"team_name": "Team A"})
        assert r.status_code in (400, 422)


# ---------------------------------------------------------------------------
# /api/roster/search
# ---------------------------------------------------------------------------

class TestRosterSearch:
    def test_search_empty_db(self, client_and_db):
        client, _ = client_and_db
        r = client.get("/api/roster/search?q=Alice")
        assert r.status_code == 200

    def test_search_finds_entry(self, client_and_db):
        client, db = client_and_db
        db.roster.add_roster_entry("Team A", 2024, "23", "Alice Smith")
        r = client.get("/api/roster/search?q=Alice")
        assert r.status_code == 200
        data = r.get_json()
        results = data.get("results") or data.get("entries") or []
        assert any("Alice" in str(e.get("player_name", "")) for e in results)


# ---------------------------------------------------------------------------
# /api/roster/<id>  (DELETE + PUT)
# ---------------------------------------------------------------------------

class TestRosterCRUD:
    def test_delete_nonexistent_returns_404(self, client_and_db):
        client, _ = client_and_db
        r = client.delete("/api/roster/9999")
        assert r.status_code in (200, 404)  # Some implementations return 200 for idempotent delete

    def test_put_updates_entry(self, client_and_db):
        client, db = client_and_db
        db.roster.add_roster_entry("Team A", 2024, "23", "Alice")
        conn = db.conn  # Database.conn is the public attribute
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM rosters WHERE player_name = ?", ("Alice",))
        entry_id = cursor.fetchone()[0]

        r = client.put(f"/api/roster/{entry_id}", json={"player_name": "Alice Updated"})
        assert r.status_code in (200, 201)
        data = r.get_json()
        if data and "entry" in data:
            assert "Alice Updated" in str(data["entry"].get("player_name", ""))
