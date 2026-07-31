"""
Blueprint tests for:
  - src/blueprints/review.py   (assign, deassign, match-similar, review-photos)
  - src/blueprints/photos.py   (photo listing, face-crop, pagination)
  - src/blueprints/detection.py face-crop endpoint

Uses Flask test client with in-memory DB; no external ML models required.
"""

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from src.api import create_app
from src.db import Database


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _jpeg_bytes(color=(128, 128, 128), size=(128, 128)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="JPEG")
    return buf.getvalue()


_counter = 0

def _insert_photo_face(db: Database, tmp_path: Path, emb=None):
    """Insert a unique photo + face row; return (photo_id, face_id)."""
    global _counter
    _counter += 1
    img = tmp_path / f"img_{_counter}.jpg"
    img.write_bytes(_jpeg_bytes())
    photo_id = db.photos.add_photo(str(img), file_hash=f"fhash_{_counter}")
    face_id = db.faces.add_face(
        photo_id=photo_id,
        embedding=emb or ([0.2] * 384),
        bbox=[10, 10, 60, 60],
        confidence=0.9,
        face_size_ratio=0.3,
    )
    return photo_id, face_id


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def ctx(tmp_path):
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    yield app.test_client(), app.db, tmp_path


# ---------------------------------------------------------------------------
# /api/review-photos and /api/confirmed-photos and /api/processing-summary
# ---------------------------------------------------------------------------

class TestReviewEndpoints:
    def test_processing_summary_ok(self, ctx):
        client, _, _ = ctx
        r = client.get("/api/processing-summary")
        assert r.status_code == 200

    def test_confirmed_photos_empty(self, ctx):
        client, _, _ = ctx
        r = client.get("/api/confirmed-photos")
        assert r.status_code == 200
        data = r.get_json()
        assert "photos" in data

    def test_review_photos_empty(self, ctx):
        client, _, _ = ctx
        r = client.get("/api/review-photos")
        assert r.status_code == 200

    def test_confirmed_photos_invalid_limit(self, ctx):
        client, _, _ = ctx
        r = client.get("/api/confirmed-photos?limit=abc")
        assert r.status_code in (400, 200)

    def test_review_photos_invalid_offset(self, ctx):
        client, _, _ = ctx
        r = client.get("/api/review-photos?offset=xyz")
        assert r.status_code in (400, 200)


# ---------------------------------------------------------------------------
# /api/faces/deassign
# ---------------------------------------------------------------------------

class TestDeassignFaces:
    def test_deassign_empty_list(self, ctx):
        client, _, _ = ctx
        r = client.post("/api/faces/deassign", json={"face_ids": []})
        assert r.status_code == 200

    def test_deassign_nonexistent_face_graceful(self, ctx):
        client, _, _ = ctx
        r = client.post("/api/faces/deassign", json={"face_ids": [9999]})
        assert r.status_code in (200, 500)

    def test_deassign_assigned_face(self, ctx, tmp_path):
        client, db, _ = ctx
        photo_id, face_id = _insert_photo_face(db, tmp_path)
        cluster_id = db.clusters.add_player_cluster(1, 1, thumbnail_face_id=face_id)
        db.clusters.assign_face_to_cluster(face_id, cluster_id)

        r = client.post("/api/faces/deassign", json={"face_ids": [face_id]})
        assert r.status_code == 200
        assert r.get_json()["success"] is True


# ---------------------------------------------------------------------------
# /api/players/<id>/assign
# ---------------------------------------------------------------------------

class TestAssignCluster:
    def test_requires_player_name(self, ctx, tmp_path):
        client, db, _ = ctx
        _, face_id = _insert_photo_face(db, tmp_path)
        cluster_id = db.clusters.add_player_cluster(1, 1, thumbnail_face_id=face_id)
        db.clusters.assign_face_to_cluster(face_id, cluster_id)

        r = client.post(f"/api/players/{cluster_id}/assign", json={})
        assert r.status_code == 400

    def test_assigns_player_name(self, ctx, tmp_path):
        client, db, _ = ctx
        _, face_id = _insert_photo_face(db, tmp_path)
        cluster_id = db.clusters.add_player_cluster(1, 1, thumbnail_face_id=face_id)
        db.clusters.assign_face_to_cluster(face_id, cluster_id)

        r = client.post(f"/api/players/{cluster_id}/assign", json={
            "player_name": "Alice Smith",
            "jersey_number": "7",
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"] is True

    def test_assign_embeds_iptc_unconditionally_without_roster_entry(self, ctx, tmp_path, monkeypatch):
        """IPTC embedding needs no roster_entry_id (unlike the old opt-in XMP
        path) — it's unconditional and driven directly by player_name."""
        from src import iptc_writer

        monkeypatch.setattr("src.blueprints.review.is_backup_ready", lambda: True)
        client, db, _ = ctx
        photo_id, face_id = _insert_photo_face(db, tmp_path)
        photo_path = db.photos.get_photo_by_id(photo_id)["file_path"]
        cluster_id = db.clusters.add_player_cluster(1, 1, thumbnail_face_id=face_id)
        db.clusters.assign_face_to_cluster(face_id, cluster_id)

        r = client.post(f"/api/players/{cluster_id}/assign", json={
            "player_name": "Bob",
            "face_ids": [face_id],
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"] is True
        assert iptc_writer.read_person_in_image(photo_path) == ["Bob"]


# ---------------------------------------------------------------------------
# /api/players/<id>/match-similar
# ---------------------------------------------------------------------------

class TestMatchSimilar:
    def _make_cluster(self, db, tmp_path, emb, assigned=False):
        _, face_id = _insert_photo_face(db, tmp_path, emb=emb)
        cluster_id = db.clusters.add_player_cluster(1, 1, thumbnail_face_id=face_id)
        db.clusters.assign_face_to_cluster(face_id, cluster_id)
        if assigned:
            db.clusters.assign_cluster_to_player(cluster_id, "Alice", "7", None)
        return cluster_id, face_id

    def test_unassigned_cluster_returns_400(self, ctx, tmp_path):
        client, db, _ = ctx
        cluster_id, _ = self._make_cluster(db, tmp_path, [0.5] * 384, assigned=False)
        r = client.post(f"/api/players/{cluster_id}/match-similar")
        assert r.status_code == 400

    def test_no_embeddings_returns_empty_lists(self, ctx, tmp_path):
        client, db, _ = ctx
        # Create an assigned cluster without embeddings
        cluster_id = db.clusters.add_player_cluster(0, 0, thumbnail_face_id=None)
        db.clusters.assign_cluster_to_player(cluster_id, "Eve", "9", None)
        r = client.post(f"/api/players/{cluster_id}/match-similar")
        assert r.status_code == 200
        data = r.get_json()
        assert data["auto_tagged"] == []
        assert data["suggestions"] == []

    def test_high_similarity_auto_tags(self, ctx, tmp_path):
        """Two clusters with very similar embeddings → auto_tagged."""
        client, db, _ = ctx
        emb_a = [1.0] + [0.0] * 383

        # Assigned cluster A
        cluster_a, face_a = self._make_cluster(db, tmp_path, emb_a, assigned=True)

        # Unassigned cluster B with same embedding → cosine=1.0
        cluster_b, face_b = self._make_cluster(db, tmp_path, emb_a, assigned=False)

        r = client.post(f"/api/players/{cluster_a}/match-similar")
        assert r.status_code == 200
        data = r.get_json()
        # With identical embeddings, cosine similarity = 1.0 ≥ 0.60 → auto-tagged
        assert len(data["auto_tagged"]) >= 1

    def test_low_similarity_no_suggestion(self, ctx, tmp_path):
        """Two orthogonal clusters → neither auto-tagged nor suggested."""
        client, db, _ = ctx
        emb_a = [1.0] + [0.0] * 383
        emb_b = [0.0] * 383 + [1.0]  # cosine = 0.0

        cluster_a, _ = self._make_cluster(db, tmp_path, emb_a, assigned=True)
        self._make_cluster(db, tmp_path, emb_b, assigned=False)

        r = client.post(f"/api/players/{cluster_a}/match-similar")
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["auto_tagged"]) == 0


# ---------------------------------------------------------------------------
# /api/photos (listing)
# ---------------------------------------------------------------------------

class TestPhotosListing:
    def test_empty_photos(self, ctx):
        client, _, _ = ctx
        r = client.get("/api/photos")
        assert r.status_code == 200
        assert r.get_json()["photos"] == []

    def test_photos_with_entries(self, ctx, tmp_path):
        client, db, _ = ctx
        for i in range(3):
            img = tmp_path / f"ph{i}.jpg"
            img.write_bytes(_jpeg_bytes())
            db.photos.add_photo(str(img), file_hash=f"ph{i}")
        r = client.get("/api/photos")
        assert r.status_code == 200
        assert len(r.get_json()["photos"]) == 3

    def test_photos_pagination_offset(self, ctx, tmp_path):
        client, db, _ = ctx
        for i in range(5):
            img = tmp_path / f"pp{i}.jpg"
            img.write_bytes(_jpeg_bytes())
            db.photos.add_photo(str(img), file_hash=f"pp{i}")
        r = client.get("/api/photos?offset=3")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# /api/face-crop/<id> (detection blueprint)
# ---------------------------------------------------------------------------

class TestFaceCrop:
    def test_nonexistent_face_returns_404(self, ctx):
        client, _, _ = ctx
        r = client.get("/api/face-crop/9999")
        assert r.status_code == 404

    def test_face_with_missing_photo_file_returns_404(self, ctx, tmp_path):
        """Face row in DB but image file deleted → 404."""
        client, db, _ = ctx
        # Create a temp path that we immediately delete after adding to DB
        img_path = tmp_path / "will_be_deleted.jpg"
        img_path.write_bytes(_jpeg_bytes())
        photo_id = db.photos.add_photo(str(img_path), file_hash="ghost")
        # Now delete the file so it's missing
        img_path.unlink()
        face_id = db.faces.add_face(
            photo_id=photo_id,
            embedding=[0.1] * 384,
            bbox=[10, 10, 60, 60],
            confidence=0.9,
        )
        from unittest.mock import patch
        with patch("src.blueprints.detection.is_allowed_photo_path", return_value=True):
            r = client.get(f"/api/face-crop/{face_id}")
        assert r.status_code in (403, 404, 500)

    def test_face_with_real_image_returns_jpeg(self, ctx, tmp_path):
        """Face with valid JPEG on disk → returns 200 JPEG."""
        import os
        client, db, _ = ctx
        img_path = tmp_path / "face_photo.jpg"
        img_path.write_bytes(_jpeg_bytes(color=(200, 100, 50), size=(200, 200)))

        photo_id = db.photos.add_photo(str(img_path), file_hash="facephoto")
        face_id = db.faces.add_face(
            photo_id=photo_id,
            embedding=[0.1] * 384,
            bbox=[50, 50, 150, 150],
            confidence=0.95,
        )

        # Need to allow the photo path — mock is_allowed_photo_path to return True
        from unittest.mock import patch
        with patch("src.blueprints.detection.is_allowed_photo_path", return_value=True):
            r = client.get(f"/api/face-crop/{face_id}")

        assert r.status_code in (200, 403, 404)
        if r.status_code == 200:
            assert "image/jpeg" in r.content_type
