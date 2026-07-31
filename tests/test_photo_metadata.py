"""Tests for src/photo_metadata.py — sparse, populated-fields-only photo metadata."""

import shutil
from pathlib import Path

import pytest

from src import photo_metadata

FIXTURE_PHOTO = Path(__file__).resolve().parent.parent / "uploads" / "DSC_3890-sm.JPG"


@pytest.fixture
def photo_path(tmp_path) -> Path:
    dest = tmp_path / "photo.jpg"
    shutil.copy2(FIXTURE_PHOTO, dest)
    return dest


def test_returns_none_for_missing_photo(db):
    assert photo_metadata.read(db, 999) is None


def test_sparse_output_has_only_image_and_library_and_people(db, photo_path):
    photo_id = db.photos.add_photo(str(photo_path))

    result = photo_metadata.read(db, photo_id)

    assert result is not None
    assert set(result.keys()) == {"file", "image", "library", "people"}
    assert "jersey_ocr" not in result
    assert "game" not in result


def test_image_section_has_real_dimensions_and_format(db, photo_path):
    photo_id = db.photos.add_photo(str(photo_path))

    result = photo_metadata.read(db, photo_id)

    assert result["image"]["width"] == 576
    assert result["image"]["height"] == 384
    assert result["image"]["format"] == "JPEG"
    assert result["image"]["size_bytes"] > 0


def test_file_section_has_basename_only(db, photo_path):
    photo_id = db.photos.add_photo(str(photo_path))

    result = photo_metadata.read(db, photo_id)

    assert result["file"]["filename"] == photo_path.name


def test_people_is_empty_list_when_no_faces(db, photo_path):
    photo_id = db.photos.add_photo(str(photo_path))

    result = photo_metadata.read(db, photo_id)

    assert result["people"] == []


def test_people_includes_player_faces_with_assignment_state(db, photo_path):
    photo_id = db.photos.add_photo(str(photo_path))
    face_id = db.faces.add_face(
        photo_id=photo_id,
        embedding=[0.1] * 8,
        bbox=[10, 10, 50, 60],
        confidence=0.95,
        quality_score=0.9,
        jersey_color="red",
        jersey_color_conf=0.8,
    )
    cluster_id = db.clusters.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=face_id)
    db.clusters.assign_face_to_cluster(face_id, cluster_id)

    result = photo_metadata.read(db, photo_id)

    assert result["people"] == [
        {"id": face_id, "cluster_id": cluster_id, "name": None, "assigned": False}
    ]

    db.clusters.assign_cluster_to_player(cluster_id, "Alice Smith", "12", None)
    result = photo_metadata.read(db, photo_id)
    assert result["people"] == [
        {"id": face_id, "cluster_id": cluster_id, "name": "Alice Smith", "assigned": True}
    ]


def test_people_excludes_low_quality_background_faces(db, photo_path):
    photo_id = db.photos.add_photo(str(photo_path))
    # Below MIN_FACE_QUALITY_SCORE / no jersey color — a background spectator,
    # not a player, matching PhotoLightbox.tsx's existing isPlayerFace filter.
    db.faces.add_face(
        photo_id=photo_id,
        embedding=[0.1] * 8,
        bbox=[400, 10, 420, 30],
        confidence=0.5,
        quality_score=0.1,
        jersey_color=None,
        jersey_color_conf=None,
    )

    result = photo_metadata.read(db, photo_id)

    assert result["people"] == []


def test_jersey_ocr_section_present_when_detected(db, photo_path):
    photo_id = db.photos.add_photo(str(photo_path))
    db.photos.add_ocr_result(photo_id, jersey_number="16", confidence=0.92, raw_text="16")

    result = photo_metadata.read(db, photo_id)

    assert result["jersey_ocr"] == {"detected_numbers": ["16"], "confidence": 0.92}


def test_game_section_absent_when_batch_has_no_team(db, photo_path):
    batch_id = db.batches.create_batch(source_folder=str(photo_path.parent))
    photo_id = db.photos.add_photo(str(photo_path), batch_id=batch_id)

    result = photo_metadata.read(db, photo_id)

    assert "game" not in result


def test_game_section_present_with_team_a_and_tournament(db, photo_path):
    batch_id = db.batches.create_batch(
        source_folder=str(photo_path.parent),
        team_name="Carleton CUT",
        team_year=2026,
        tournament="Nationals",
    )
    photo_id = db.photos.add_photo(str(photo_path), batch_id=batch_id)

    result = photo_metadata.read(db, photo_id)

    assert result["game"] == {"team_a": "Carleton CUT", "year": 2026, "tournament": "Nationals"}


def test_game_section_derives_team_b_from_game_context(db, photo_path):
    batch_id = db.batches.create_batch(
        source_folder=str(photo_path.parent),
        team_name="Carleton CUT",
        team_year=2026,
        tournament="Nationals",
    )
    photo_id = db.photos.add_photo(str(photo_path), batch_id=batch_id)
    db.context.set_game_context([
        {"team_name": "Carleton CUT", "team_year": 2026, "uniform_color": "black"},
        {"team_name": "UBC Thunderbirds", "team_year": 2026, "uniform_color": "white"},
    ])

    result = photo_metadata.read(db, photo_id)

    assert result["game"]["team_b"] == "UBC Thunderbirds"


def test_library_section_has_ingested_and_batch_name(db, photo_path):
    batch_id = db.batches.create_batch(source_folder=str(photo_path.parent), name="uploads")
    photo_id = db.photos.add_photo(str(photo_path), batch_id=batch_id)

    result = photo_metadata.read(db, photo_id)

    assert result["library"]["batch"] == "uploads"
    assert result["library"]["batch_id"] == batch_id
    assert result["library"]["ingested"]
