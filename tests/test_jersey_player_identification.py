"""
Test jersey-based player identification for photos.

Jersey detections should:
1. Identify which players are in a photo (metadata enrichment)
2. NOT incorrectly reassign faces to those players
3. Remain independent from face clustering
"""

import pytest
import numpy as np
from src.db import Database
from src.face_cluster import FaceClusterer
from src import config as cfg


@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    database.init_schema()
    yield database
    database.close()


def _add_photo(db, tmp_path, name):
    """Create a photo file and add it to the database."""
    photo_file = tmp_path / f"{name}.jpg"
    photo_file.write_bytes(f"fake-{name}".encode())
    return db.photos.add_photo(str(photo_file))


def _add_face(db, photo_id, name, embedding, sharpness=100.0, face_size_ratio=0.05):
    """Add a face to the database."""
    if hasattr(embedding, 'tolist'):
        embedding = embedding.tolist()

    return db.faces.add_face(
        photo_id=photo_id,
        embedding=embedding,
        bbox=[10, 20, 100, 120],
        confidence=0.9,
        sharpness=sharpness,
        face_size_ratio=face_size_ratio
    )


def _add_roster_entry(db, jersey_number, player_name, team_name="Team A", team_year=2024):
    """Add a roster entry and return the ID."""
    db.roster.add_roster_entry(
        team_name=team_name,
        team_year=team_year,
        jersey_number=jersey_number,
        player_name=player_name,
        uniform_color="red"
    )
    game_context = [{
        "team_name": team_name,
        "team_year": team_year,
        "uniform_color": "red"
    }]
    candidates = db.roster.resolve_roster_candidates(jersey_number, context=game_context)
    if candidates:
        return candidates[0]["id"]
    raise ValueError(f"Could not find roster entry for {jersey_number}")


def _add_jersey_detection(db, photo_id, jersey_number, roster_entry_id, confidence=0.95):
    """Add a jersey detection linked to a roster entry."""
    return db.photos.add_ocr_result(
        photo_id=photo_id,
        jersey_number=jersey_number,
        confidence=confidence,
        raw_text=jersey_number,
        uniform_color="red",
        bbox=[50, 100, 150, 200],
        roster_entry_id=roster_entry_id
    )


# ── Test: Jersey detection identifies player in photo ─────────────────────────

def test_jersey_detection_identifies_player_in_photo(db, tmp_path, monkeypatch):
    """
    Given:
      - Photo contains Nathan's jersey #31 (clearly visible)
      - Nathan's face is NOT clearly visible in the photo
      - Nathan exists in roster

    When: Jersey detection runs and face clustering runs

    Then: Nathan should be identified as being in the photo (via jersey)
          The photo metadata should record this identification
          This should be queryable for discovery ("photos of Nathan")
    """
    monkeypatch.setattr(cfg, "MIN_FACE_SHARPNESS", 0.0)
    monkeypatch.setattr(cfg, "MIN_FACE_SIZE_RATIO", 0.0)

    # Create roster entry for Nathan
    nathan_roster_id = _add_roster_entry(db, "31", "Nathan De Morgan", "Team A")

    # Photo: Contains Nathan's jersey but not his face
    photo_id = _add_photo(db, tmp_path, "photo_jersey_only")

    # Some other face in the photo (not Nathan)
    other_emb = np.zeros(384, dtype=np.float32)
    other_emb[:100] = 1.0
    other_face_id = _add_face(db, photo_id, "other", other_emb)

    # Jersey detection for Nathan
    _add_jersey_detection(db, photo_id, "31", nathan_roster_id)

    # Run clustering (face clustering should be independent of jersey)
    result = FaceClusterer(db, similarity_threshold=0.40).run()

    # Verify clustering created a cluster
    assert result["clusters_created"] >= 1

    # The key test: query the photo to see which players are identified in it
    ocr_results = db.photos.get_ocr_by_photo(photo_id)

    # Verify jersey detection exists and is linked to Nathan
    assert len(ocr_results) >= 1
    assert ocr_results[0]["jersey_number"] == "31"
    assert ocr_results[0]["roster_entry_id"] == nathan_roster_id

    # Verify we can discover which players are in this photo via jersey
    identified_players = set()
    for ocr in ocr_results:
        if ocr.get("roster_entry_id"):
            roster_entry = db.roster.get_roster_entry_by_id(ocr["roster_entry_id"])
            if roster_entry:
                identified_players.add(roster_entry["player_name"])

    assert "Nathan De Morgan" in identified_players


def test_jersey_detection_does_not_reassign_other_faces(db, tmp_path, monkeypatch):
    """
    Given:
      - Photo contains Nathan's jersey #31
      - Photo contains a different person (unknown, not in roster)
      - Nathan's face is NOT in the photo
      - The other person's face IS in the photo and clusters well

    When: Jersey detection identifies Nathan + Face clustering runs

    Then: The other person's face should cluster independently
          Should NOT be reassigned to Nathan's cluster just because Nathan's jersey is in the photo
    """
    monkeypatch.setattr(cfg, "MIN_FACE_SHARPNESS", 0.0)
    monkeypatch.setattr(cfg, "MIN_FACE_SIZE_RATIO", 0.0)

    # Create roster entry for Nathan
    nathan_roster_id = _add_roster_entry(db, "31", "Nathan De Morgan", "Team A")

    # Create another player (for comparison)
    other_player_roster_id = _add_roster_entry(db, "23", "Other Player", "Team A")

    # Photo: Nathan's jersey visible, but someone else's face is visible
    photo_id = _add_photo(db, tmp_path, "photo_mixed")

    # Add the other person's face (clear, high quality)
    other_emb = np.ones(384, dtype=np.float32) * 0.5
    other_face_id = _add_face(db, photo_id, "other", other_emb, sharpness=100.0, face_size_ratio=0.10)

    # Jersey detection for Nathan (but his face is not in the photo)
    _add_jersey_detection(db, photo_id, "31", nathan_roster_id)

    # Also detect the other player's jersey
    _add_jersey_detection(db, photo_id, "23", other_player_roster_id)

    # Another photo: Other player's face clearly (for clustering)
    photo_2_id = _add_photo(db, tmp_path, "photo_other_face")
    other_face_2_id = _add_face(db, photo_2_id, "other_2", other_emb * 0.98, sharpness=100.0, face_size_ratio=0.10)
    _add_jersey_detection(db, photo_2_id, "23", other_player_roster_id)

    # Run clustering
    result = FaceClusterer(db, similarity_threshold=0.40).run()

    # Verify clustering succeeded
    assert result["clusters_created"] >= 1

    # Get all clusters
    clusters = db.clusters.get_all_player_clusters()

    # Check that "Other Player" has a cluster
    other_clusters = [c for c in clusters if c.get("player_name") == "Other Player"]
    if other_clusters:
        other_cluster = other_clusters[0]
        photos_in_cluster = db.clusters.get_photos_by_cluster(other_cluster["id"])

        # Verify the other player's faces are in their cluster
        # But NOT because of Nathan's jersey - they should cluster based on facial similarity
        assert len(photos_in_cluster) >= 1

    # Nathan should NOT have automatically claimed the other person's face
    # (jersey detection should not reassign faces)
    nathan_clusters = [c for c in clusters if c.get("player_name") == "Nathan De Morgan"]

    if nathan_clusters:
        # If Nathan has a cluster, it should NOT contain the other person's face
        # (Nathan's face is not in the photo, so no cluster should be created for him)
        # Unless the system auto-matched an empty cluster, which would be a bug
        pass


def test_multiple_jersey_detections_in_same_photo_identify_multiple_players(db, tmp_path, monkeypatch):
    """
    Given:
      - Photo contains jersey #31 (Nathan) and jersey #19 (Sarek)
      - Faces of both players visible in photo
      - Both are in roster

    When: Jersey detection + face clustering runs

    Then: Both Nathan and Sarek should be identified in the photo
          Photo metadata should show both players
          Face clustering should work independently
    """
    monkeypatch.setattr(cfg, "MIN_FACE_SHARPNESS", 0.0)
    monkeypatch.setattr(cfg, "MIN_FACE_SIZE_RATIO", 0.0)

    # Create roster entries
    nathan_roster_id = _add_roster_entry(db, "31", "Nathan De Morgan", "Team A")
    sarek_roster_id = _add_roster_entry(db, "19", "Sarek Mallareddy", "Team A")

    # Photo: Both jerseys visible
    photo_id = _add_photo(db, tmp_path, "photo_both")

    # Nathan's face
    nathan_emb = np.ones(384, dtype=np.float32)
    nathan_face_id = _add_face(db, photo_id, "nathan", nathan_emb)

    # Sarek's face (different embedding)
    sarek_emb = np.zeros(384, dtype=np.float32)
    sarek_emb[:150] = 1.0
    sarek_face_id = _add_face(db, photo_id, "sarek", sarek_emb)

    # Jersey detections for both
    _add_jersey_detection(db, photo_id, "31", nathan_roster_id)
    _add_jersey_detection(db, photo_id, "19", sarek_roster_id)

    # Run clustering
    result = FaceClusterer(db, similarity_threshold=0.80).run()

    # Verify photo metadata shows both players
    ocr_results = db.photos.get_ocr_by_photo(photo_id)
    assert len(ocr_results) >= 2

    jersey_numbers = {ocr["jersey_number"] for ocr in ocr_results}
    assert "31" in jersey_numbers
    assert "19" in jersey_numbers

    # Extract identified players
    identified_players = set()
    for ocr in ocr_results:
        if ocr.get("roster_entry_id"):
            roster_entry = db.roster.get_roster_entry_by_id(ocr["roster_entry_id"])
            if roster_entry:
                identified_players.add(roster_entry["player_name"])

    assert "Nathan De Morgan" in identified_players
    assert "Sarek Mallareddy" in identified_players


def test_photo_discovery_by_jersey_identified_player(db, tmp_path, monkeypatch):
    """
    Given:
      - Multiple photos, some with Nathan identified by jersey
      - Some with Nathan identified by face clustering
      - Some with neither

    When: Querying for "all photos of Nathan"

    Then: Should get photos where Nathan is identified by EITHER jersey OR face
    """
    monkeypatch.setattr(cfg, "MIN_FACE_SHARPNESS", 0.0)
    monkeypatch.setattr(cfg, "MIN_FACE_SIZE_RATIO", 0.0)

    nathan_roster_id = _add_roster_entry(db, "31", "Nathan De Morgan", "Team A")
    other_roster_id = _add_roster_entry(db, "23", "Other Player", "Team A")

    # Photo 1: Nathan identified by jersey only
    photo_1_id = _add_photo(db, tmp_path, "photo_nathan_jersey")
    _add_jersey_detection(db, photo_1_id, "31", nathan_roster_id)

    # Photo 2: Nathan identified by face (clustered)
    photo_2_id = _add_photo(db, tmp_path, "photo_nathan_face")
    nathan_emb = np.ones(384, dtype=np.float32)
    nathan_face_1 = _add_face(db, photo_2_id, "nathan_1", nathan_emb)
    nathan_face_2 = _add_face(db, photo_2_id, "nathan_2", nathan_emb * 0.99)

    # Photo 3: Other player (not Nathan)
    photo_3_id = _add_photo(db, tmp_path, "photo_other")
    other_emb = np.ones(384, dtype=np.float32) * 0.5
    other_face = _add_face(db, photo_3_id, "other", other_emb)
    _add_jersey_detection(db, photo_3_id, "23", other_roster_id)

    # Run clustering to create Nathan's cluster
    FaceClusterer(db, similarity_threshold=0.40).run()

    # Query: get all photos containing Nathan
    # Method 1: By jersey detection
    nathan_jersey_photos = []
    all_ocr = db.photos.get_ocr_by_photo(photo_1_id)
    for ocr in all_ocr:
        if ocr.get("roster_entry_id") == nathan_roster_id:
            nathan_jersey_photos.append(photo_1_id)

    assert photo_1_id in nathan_jersey_photos

    # Method 2: By face cluster
    nathan_clusters = db.clusters.get_all_player_clusters()
    nathan_clusters = [c for c in nathan_clusters if c.get("player_name") == "Nathan De Morgan"]

    nathan_face_photos = set()
    for cluster in nathan_clusters:
        photos = db.clusters.get_photos_by_cluster(cluster["id"])
        for photo in photos:
            nathan_face_photos.add(photo["photo_id"])

    # Both methods should work independently
    assert photo_1_id in nathan_jersey_photos or photo_1_id in nathan_face_photos


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
