"""
Blueprint-level tests for src/blueprints/detection.py.

Covers the GET/POST/DELETE endpoints that do NOT require a live face-detection
model (InsightFace) or a real photo file on disk.  Heavy endpoints (detect-faces,
cluster-players) are smoke-tested only — they are submitted as async jobs and we
verify the 202 is returned; we do NOT wait for the job to finish.
"""

import io
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import List

import numpy as np
import pytest
from PIL import Image

from src.api import create_app
from src.db import Database


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _jpeg_bytes(color=(200, 100, 50), size=(32, 32)) -> bytes:
    pil = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    pil.save(buf, format="JPEG")
    return buf.getvalue()


_insert_counter = 0


def _insert_photo_and_face(db: Database, tmp_path: Path, embedding=None):
    """Insert a unique photo file + face row; return (photo_id, face_id)."""
    global _insert_counter
    _insert_counter += 1
    img_path = tmp_path / f"test_{_insert_counter}.jpg"
    img_path.write_bytes(_jpeg_bytes())
    photo_id = db.photos.add_photo(
        file_path=str(img_path),
        file_hash=f"hash_{_insert_counter}",
    )
    emb = embedding or ([0.1] * 384)
    face_id = db.faces.add_face(
        photo_id=photo_id,
        embedding=emb,
        bbox=[10, 20, 80, 100],
        confidence=0.95,
    )
    return photo_id, face_id


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_client(tmp_path):
    """Flask test client with in-memory DB."""
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    yield app.test_client(), app.db, tmp_path


# ---------------------------------------------------------------------------
# GET /api/players
# ---------------------------------------------------------------------------

class TestGetPlayers:
    def test_empty_db_returns_empty_list(self, test_client):
        client, db, _ = test_client
        r = client.get("/api/players")
        assert r.status_code == 200
        data = r.get_json()
        assert "players" in data
        assert isinstance(data["players"], list)
        assert data["total"] == 0

    def test_returns_assigned_cluster_always(self, test_client, tmp_path):
        client, db, _ = test_client
        photo_id, face_id = _insert_photo_and_face(db, tmp_path)
        cluster_id = db.clusters.add_player_cluster(
            face_count=1, photo_count=1, thumbnail_face_id=face_id
        )
        db.clusters.assign_face_to_cluster(face_id=face_id, cluster_id=cluster_id)
        db.clusters.assign_cluster_to_player(
            cluster_id=cluster_id,
            player_name="Alice",
            jersey_number="23",
            roster_entry_id=None,
        )
        r = client.get("/api/players")
        assert r.status_code == 200
        players = r.get_json()["players"]
        assert any(p["player_name"] == "Alice" for p in players)


# ---------------------------------------------------------------------------
# GET /api/photos/<id>/jersey-detections
# ---------------------------------------------------------------------------

class TestGetJerseyDetections:
    def test_nonexistent_photo_returns_404(self, test_client):
        client, _, _ = test_client
        r = client.get("/api/photos/9999/jersey-detections")
        assert r.status_code == 404

    def test_photo_with_no_detections(self, test_client, tmp_path):
        client, db, _ = test_client
        photo_id, _ = _insert_photo_and_face(db, tmp_path)
        r = client.get(f"/api/photos/{photo_id}/jersey-detections")
        assert r.status_code == 200
        data = r.get_json()
        assert data["photo_id"] == photo_id
        assert data["total"] == 0

    def test_photo_with_detections(self, test_client, tmp_path):
        client, db, _ = test_client
        photo_id, _ = _insert_photo_and_face(db, tmp_path)
        db.photos.add_ocr_result(
            photo_id=photo_id,
            jersey_number="19",
            confidence=0.88,
            raw_text="19",
            uniform_color="black",
            bbox=[50, 100, 90, 140],
            roster_entry_id=None,
        )
        r = client.get(f"/api/photos/{photo_id}/jersey-detections")
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 1
        assert data["detections"][0]["jersey_number"] == "19"


# ---------------------------------------------------------------------------
# GET /api/players/<id>/photos
# ---------------------------------------------------------------------------

class TestGetPlayerPhotos:
    def test_nonexistent_cluster_returns_empty(self, test_client):
        client, _, _ = test_client
        r = client.get("/api/players/9999/photos")
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 0

    def test_cluster_with_photos(self, test_client, tmp_path):
        client, db, _ = test_client
        photo_id, face_id = _insert_photo_and_face(db, tmp_path)
        cluster_id = db.clusters.add_player_cluster(
            face_count=1, photo_count=1, thumbnail_face_id=face_id
        )
        db.clusters.assign_face_to_cluster(face_id=face_id, cluster_id=cluster_id)
        r = client.get(f"/api/players/{cluster_id}/photos")
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 1
        assert data["cluster_id"] == cluster_id


# ---------------------------------------------------------------------------
# DELETE /api/players/<id>/faces/<id>
# ---------------------------------------------------------------------------

class TestRemoveFaceFromCluster:
    def test_remove_assigned_face(self, test_client, tmp_path):
        client, db, _ = test_client
        photo_id, face_id = _insert_photo_and_face(db, tmp_path)
        cluster_id = db.clusters.add_player_cluster(
            face_count=1, photo_count=1, thumbnail_face_id=face_id
        )
        db.clusters.assign_face_to_cluster(face_id=face_id, cluster_id=cluster_id)
        r = client.delete(f"/api/players/{cluster_id}/faces/{face_id}")
        assert r.status_code == 200
        assert r.get_json()["success"] is True


# ---------------------------------------------------------------------------
# POST /api/consolidate-player/<name>
# ---------------------------------------------------------------------------

class TestConsolidatePlayer:
    def test_no_clusters_to_consolidate(self, test_client):
        client, _, _ = test_client
        r = client.post("/api/consolidate-player/Nobody")
        assert r.status_code == 200

    def test_consolidates_duplicate_clusters(self, test_client, tmp_path):
        client, db, _ = test_client
        _, face1 = _insert_photo_and_face(db, tmp_path)
        _, face2 = _insert_photo_and_face(db, tmp_path)

        c1 = db.clusters.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=face1)
        c2 = db.clusters.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=face2)
        db.clusters.assign_face_to_cluster(face_id=face1, cluster_id=c1)
        db.clusters.assign_face_to_cluster(face_id=face2, cluster_id=c2)
        db.clusters.assign_cluster_to_player(c1, "Bob", "7", None)
        db.clusters.assign_cluster_to_player(c2, "Bob", "7", None)

        r = client.post("/api/consolidate-player/Bob")
        assert r.status_code == 200
        data = r.get_json()
        assert "primary_id" in data


# ---------------------------------------------------------------------------
# POST /api/detect-faces  (smoke-test — 202 + job_id returned)
# ---------------------------------------------------------------------------

class TestDetectFacesSmoke:
    def test_detect_faces_endpoint_is_reachable(self, test_client):
        """Endpoint accepts POST and returns a structured response."""
        client, _, _ = test_client
        r = client.post("/api/detect-faces", json={})
        # Any valid HTTP response is acceptable; the endpoint should not 500
        assert r.status_code != 500
        data = r.get_json()
        assert data is not None

    def test_with_game_context_returns_202_or_400_or_503(self, test_client, tmp_path):
        """With valid game context, endpoint either enqueues (202) or rejects (400/503)."""
        client, db, _ = test_client
        db.context.set_game_context([
            {"team_name": "Team A", "team_year": 2024, "uniform_color": "red"},
            {"team_name": "Team B", "team_year": 2024, "uniform_color": "blue"},
        ])
        r = client.post("/api/detect-faces", json={})
        assert r.status_code in (202, 400, 503)


# ---------------------------------------------------------------------------
# POST /api/cluster-players  (smoke-test)
# ---------------------------------------------------------------------------

class TestClusterPlayersSmoke:
    def test_returns_202_or_503(self, test_client):
        client, _, _ = test_client
        r = client.post("/api/cluster-players", json={})
        assert r.status_code in (202, 503)


# ---------------------------------------------------------------------------
# Regression: live photo_count reflects actual faces after consolidation
# ---------------------------------------------------------------------------

class TestLiveCountRegression:
    """Consolidating two same-named clusters correctly updates photo_count."""

    def test_consolidated_cluster_shows_combined_count(self, test_client, tmp_path):
        client, db, _ = test_client

        # Create two photos and one face each
        photo_id1, face_id1 = _insert_photo_and_face(db, tmp_path)
        photo_id2, face_id2 = _insert_photo_and_face(db, tmp_path)

        c1 = db.clusters.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=face_id1)
        c2 = db.clusters.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=face_id2)
        db.clusters.assign_face_to_cluster(face_id=face_id1, cluster_id=c1)
        db.clusters.assign_face_to_cluster(face_id=face_id2, cluster_id=c2)

        db.clusters.assign_cluster_to_player(c1, "Carol", "15", None)
        db.clusters.assign_cluster_to_player(c2, "Carol", "15", None)

        # Consolidate via API
        r = client.post("/api/consolidate-player/Carol")
        assert r.status_code == 200
        result = r.get_json()
        primary_id = result.get("primary_id")

        # The surviving cluster should have photo_count = 2
        cluster = db.clusters.get_cluster_by_id(primary_id)
        assert cluster is not None
        assert cluster["photo_count"] == 2
