"""Read-only, sparse metadata projection for a single photo (feature #1).

Composes existing repositories into one dict — every key present is
populated; a section with no data is simply absent, never present-but-empty
(except `people`, which is always present so the panel can show "0 of N
identified").

Game section note: `photo_batches` only carries this batch's own team
(`team_name`/`team_year`/`tournament`) — there is no `team_a`/`team_b` pair on
the batch. The second team comes from the existing global
`game_context_teams` table (`db.context.get_game_context()`), the same
opponent-derivation logic already used by the assign-metadata write path:
whichever context team isn't this batch's team is `team_b`, if exactly one
candidate exists.
"""

import os
from typing import Optional

from PIL import Image

from src.config import MIN_FACE_QUALITY_SCORE, MIN_JERSEY_COLOR_CONF
from src.db import Database


def _is_player_face(face: dict) -> bool:
    """Mirrors PhotoLightbox.tsx's isPlayerFace: quality + jersey-color gate
    that excludes background spectators from crowd shots."""
    quality = face.get("quality_score") or 0
    jersey_conf = face.get("jersey_color_conf") or 0
    return bool(face.get("jersey_color")) and quality >= MIN_FACE_QUALITY_SCORE and jersey_conf >= MIN_JERSEY_COLOR_CONF


def read(db: Database, photo_id: int) -> Optional[dict]:
    """Return a sparse metadata dict for photo_id, or None if not found."""
    photo = db.photos.get_photo_by_id(photo_id)
    if not photo:
        return None

    result: dict = {"file": {"filename": os.path.basename(photo["file_path"])}}

    image_section = _read_image_section(photo["file_path"], photo.get("file_size"))
    if image_section:
        result["image"] = image_section

    result["library"] = _read_library_section(db, photo)

    jersey_section = _read_jersey_section(db, photo_id)
    if jersey_section:
        result["jersey_ocr"] = jersey_section

    batch = db.batches.get_batch(photo["batch_id"]) if photo.get("batch_id") else None
    game_section = _read_game_section(db, batch)
    if game_section:
        result["game"] = game_section

    result["people"] = _read_people_section(db, photo_id)

    return result


def _read_image_section(file_path: str, file_size: Optional[int]) -> Optional[dict]:
    if not file_path or not os.path.exists(file_path):
        return None
    with Image.open(file_path) as img:
        width, height = img.size
        image_format = img.format
        mode = img.mode
    return {
        "width": width,
        "height": height,
        "size_bytes": file_size,
        "format": image_format,
        "mode": mode,
    }


def _read_library_section(db: Database, photo: dict) -> dict:
    section = {"ingested": photo.get("ingested_at")}
    batch_id = photo.get("batch_id")
    if batch_id:
        section["batch_id"] = batch_id
        batch = db.batches.get_batch(batch_id)
        if batch:
            batch_name = batch.get("name") or os.path.basename(batch.get("source_folder") or "") or None
            if batch_name:
                section["batch"] = batch_name
    return section


def _read_jersey_section(db: Database, photo_id: int) -> Optional[dict]:
    ocr_rows = db.photos.get_ocr_by_photo(photo_id)
    detections = [row for row in ocr_rows if row.get("jersey_number")]
    if not detections:
        return None
    confidences = [row["confidence"] for row in detections if row.get("confidence") is not None]
    section = {"detected_numbers": [row["jersey_number"] for row in detections]}
    if confidences:
        section["confidence"] = max(confidences)
    return section


def _read_game_section(db: Database, batch: Optional[dict]) -> Optional[dict]:
    if not batch:
        return None

    team_a = batch.get("team_name")
    team_b = None
    if team_a:
        context = db.context.get_game_context()
        opponents = [team for team in context if team["team_name"] != team_a]
        if len(opponents) == 1:
            team_b = opponents[0]["team_name"]

    fields = {
        "team_a": team_a,
        "team_b": team_b,
        "year": batch.get("team_year"),
        "tournament": batch.get("tournament"),
    }
    populated = {key: value for key, value in fields.items() if value}
    return populated or None


def _read_people_section(db: Database, photo_id: int) -> list:
    faces = db.faces.get_faces_with_player_info_by_photo(photo_id)
    return [
        {
            "id": face["face_id"],
            "cluster_id": face["cluster_id"],
            "name": face["player_name"],
            "assigned": face["player_name"] is not None,
        }
        for face in faces
        if _is_player_face(face)
    ]
