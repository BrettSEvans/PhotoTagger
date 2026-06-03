"""Face detection, clustering, and face serving endpoints."""

import io
import logging
import os
from pathlib import Path
from flask import Blueprint, request, jsonify, send_file, current_app
import numpy as np
import cv2
from src.utils import parse_float, is_allowed_photo_path

logger = logging.getLogger(__name__)
bp = Blueprint("detection", __name__)


@bp.route("/api/detect-faces", methods=["POST"])
def detect_faces_endpoint():
    """
    Run face detection and jersey number recognition on all photos.

    JSON body (optional):
    {
        "photo_ids": [1, 2, 3]  // Optional: process specific photos
    }

    Returns a job ID for async processing. The job will:
    1. Validate game context has jersey colors for both teams
    2. Run face detection (existing)
    3. Run jersey number recognition and roster matching (new)
    4. Return combined results
    """
    from src.face_detector import FaceDetector
    from src.uniform_detector import UniformDetector
    from src.jersey_recognition import JerseyRecognizer

    db = current_app.db
    app_job_runner = current_app.job_runner

    data = request.get_json() or {}
    photo_ids = data.get("photo_ids", None)

    try:
        # Validate game context has jersey colors before starting detection
        game_context = db.context.get_game_context()
        missing_colors = []
        for team in game_context:
            if not team.get("uniform_color") or not team.get("uniform_color").strip():
                missing_colors.append(team.get("team_name", "Unknown team"))

        if missing_colors:
            error_msg = f"Jersey colors required for player matching. Missing colors for: {', '.join(missing_colors)}. Please fill out the Game Context card."
            logger.warning(f"detect-faces validation failed: {error_msg}")
            return jsonify({"error": error_msg, "code": "MISSING_JERSEY_COLORS"}), 400

        def run_detection(job_id: int):
            detector = FaceDetector()
            uniform = UniformDetector()
            recognizer = JerseyRecognizer(db)
            photos = db.photos.get_all_photos()

            if photo_ids:
                photos = [p for p in photos if p["id"] in set(photo_ids)]

            total_faces = 0
            total_jersey_detections = 0
            jersey_matched = 0
            errors = 0
            skipped_existing = 0

            # Phase 1: Face detection
            for idx, photo in enumerate(photos):
                photo_id = photo["id"]
                file_path = photo.get("file_path", "")
                filename = Path(file_path).name if file_path else f"photo_{photo_id}"

                if not file_path or not os.path.exists(file_path):
                    continue
                if db.faces.photo_has_faces(photo_id):
                    skipped_existing += 1
                    continue
                try:
                    faces = detector.detect_faces(file_path)
                    # Load the image once (BGR) so we can sample each face's torso color
                    img_bgr = cv2.imread(file_path) if faces else None
                    for face in faces:
                        emb_list = face["embedding"].tolist() if hasattr(face["embedding"], "tolist") else face["embedding"]
                        jersey_color, jersey_conf = (None, None)
                        if img_bgr is not None:
                            jersey_color, jersey_conf, _ = uniform.sample_face_jersey(img_bgr, face["bbox"])
                        db.faces.add_face(
                            photo_id=photo_id,
                            embedding=emb_list,
                            bbox=face["bbox"],
                            confidence=face["confidence"],
                            sharpness=face.get("sharpness"),
                            face_size_ratio=face.get("face_size_ratio"),
                            quality_score=face.get("quality_score"),
                            jersey_color=jersey_color,
                            jersey_color_conf=jersey_conf,
                        )
                    total_faces += len(faces)

                    # Update job with per-photo progress message (phase 1: 0-70%)
                    progress = int((idx + 1) / max(len(photos), 1) * 70)
                    db.jobs.update_processing_job(
                        job_id,
                        progress=progress,
                        result={"current_file": filename, "faces_detected": total_faces}
                    )
                    logger.info(f"Detected {len(faces)} face(s) in {filename}")
                except Exception as e:
                    logger.error(f"Face detection error on photo {photo_id}: {e}")
                    errors += 1

            # Phase 2: Jersey number recognition and roster matching
            logger.info("Starting jersey number recognition...")
            try:
                photo_ids_to_process = [p["id"] for p in photos]
                jersey_matches = recognizer.process_photos(photo_ids_to_process, game_context)
                for detections in jersey_matches.values():
                    total_jersey_detections += len(detections)
                    jersey_matched += sum(1 for d in detections if d.get("roster_entry_id"))
            except Exception as e:
                logger.error(f"Jersey recognition error: {e}")
                errors += 1

            # Update job to completion
            db.jobs.update_processing_job(
                job_id,
                progress=100,
                result={
                    "photos_processed": len(photos),
                    "faces_detected": total_faces,
                    "jersey_detections": total_jersey_detections,
                    "matched_to_roster": jersey_matched,
                    "photos_skipped_existing": skipped_existing,
                    "errors": errors,
                }
            )

            return {
                "photos_processed": len(photos),
                "faces_detected": total_faces,
                "jersey_detections": total_jersey_detections,
                "matched_to_roster": jersey_matched,
                "photos_skipped_existing": skipped_existing,
                "errors": errors,
            }

        job_id = app_job_runner.submit("detect_faces", {"photo_ids": photo_ids}, run_detection)
        job = db.jobs.get_processing_job(job_id)
        return jsonify({"success": True, "job_id": job_id, "job": job}), 202

    except Exception as e:
        logger.error(f"detect-faces error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/backfill-jersey-colors", methods=["POST"])
def backfill_jersey_colors():
    """
    Sample the jersey color for every already-detected face from the image on disk.

    Lets the new per-face color signal be applied to faces that were detected
    before jersey sampling existed — no need to re-run the slow InsightFace pass.
    Re-cluster afterwards for the colors to affect the player list.
    """
    from src.uniform_detector import UniformDetector

    db = current_app.db
    app_job_runner = current_app.job_runner

    try:
        def run_backfill(job_id: int):
            uniform = UniformDetector()
            faces = db.faces.get_faces_with_paths()
            updated = 0
            errors = 0
            img_cache_path = None
            img_bgr = None

            for i, face in enumerate(faces):
                file_path = face["file_path"]
                if not file_path or not os.path.exists(file_path):
                    continue
                try:
                    # Reuse the loaded image across consecutive faces in the same photo
                    if file_path != img_cache_path:
                        img_bgr = cv2.imread(file_path)
                        img_cache_path = file_path
                    if img_bgr is None:
                        continue
                    color, conf, _ = uniform.sample_face_jersey(img_bgr, face["bbox"])
                    db.faces.set_jersey_color(face["id"], color, conf)
                    updated += 1
                except Exception as e:
                    logger.error(f"jersey backfill error on face {face['id']}: {e}")
                    errors += 1

                if i % 25 == 0:
                    progress = int((i + 1) / max(len(faces), 1) * 100)
                    db.jobs.update_processing_job(job_id, progress=progress)

            return {"faces_total": len(faces), "faces_updated": updated, "errors": errors}

        job_id = app_job_runner.submit("backfill_jersey_colors", {}, run_backfill)
        job = db.jobs.get_processing_job(job_id)
        return jsonify({"success": True, "job_id": job_id, "job": job}), 202
    except Exception as e:
        logger.error(f"backfill-jersey-colors error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/cluster-players", methods=["POST"])
def cluster_players():
    """Cluster all detected faces into player identities."""
    from src.face_cluster import FaceClusterer

    db = current_app.db
    app_job_runner = current_app.job_runner

    data = request.get_json() or {}
    threshold = parse_float(data.get("threshold", 0.40))
    if threshold is None:
        return jsonify({"error": "threshold must be a number"}), 400

    try:
        def run_clustering(job_id: int):
            clusterer = FaceClusterer(db, similarity_threshold=threshold)
            return clusterer.run()

        job_id = app_job_runner.submit("cluster_players", {"threshold": threshold}, run_clustering)
        job = db.jobs.get_processing_job(job_id)
        return jsonify({"success": True, "job_id": job_id, "job": job}), 202
    except Exception as e:
        logger.error(f"cluster-players error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/players", methods=["GET"])
def get_players():
    """Get player clusters worth reviewing (recurring, prominent, or already assigned)."""
    from src.config import MIN_CLUSTER_PHOTOS, MIN_CLUSTER_PROMINENCE

    db = current_app.db
    try:
        clusters = db.clusters.get_all_player_clusters(
            min_photos=MIN_CLUSTER_PHOTOS,
            min_prominence=MIN_CLUSTER_PROMINENCE,
        )
        return jsonify({
            "players": clusters,
            "total": len(clusters),
        }), 200
    except Exception as e:
        logger.error(f"get-players error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/photos/<int:photo_id>/jersey-detections", methods=["GET"])
def get_jersey_detections_for_photo(photo_id: int):
    """Get all jersey number detections for a specific photo with roster information.

    Returns:
    {
        "photo_id": 2684,
        "detections": [
            {
                "id": 105,
                "jersey_number": "31",
                "confidence": 0.94,
                "bbox": [x0, y0, x1, y1],
                "roster_entry_id": 42,
                "player_name": "Nathan De Morgan",
                "team_name": "Carleton (CUT)",
                "uniform_color": "red"
            },
            ...
        ],
        "total": 2
    }
    """
    db = current_app.db

    try:
        # Verify photo exists
        photo = db.photos.get_photo_by_id(photo_id)
        if not photo:
            return jsonify({"error": "Photo not found"}), 404

        # Get jersey detections with roster info
        detections = db.photos.get_jersey_detections(photo_id)

        return jsonify({
            "photo_id": photo_id,
            "detections": detections,
            "total": len(detections),
        }), 200

    except Exception as e:
        logger.error(f"get-jersey-detections error for photo {photo_id}: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/players/<int:cluster_id>/photos", methods=["GET"])
def get_player_photos(cluster_id: int):
    """Get all photos containing a specific player."""
    db = current_app.db
    min_face_confidence = parse_float(request.args.get("min_face_confidence", "0.0"))
    if min_face_confidence is None:
        return jsonify({"error": "min_face_confidence must be a number"}), 400

    try:
        photos = db.clusters.get_photos_by_cluster(cluster_id, min_face_confidence)
        return jsonify({
            "cluster_id": cluster_id,
            "photos": [
                {
                    "id": p["id"],
                    "filename": os.path.basename(p["file_path"]),
                    "path": p["file_path"],
                    "added_at": p["added_at"],
                    "face_id": p["face_id"],
                    "face_bbox": p["face_bbox"],
                    "face_confidence": p["face_confidence"],
                }
                for p in photos
            ],
            "total": len(photos),
        }), 200
    except Exception as e:
        logger.error(f"get-player-photos error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/face-crop/<int:face_id>", methods=["GET"])
def serve_face_crop(face_id: int):
    """Serve a cropped face image (with padding) as JPEG."""
    db = current_app.db
    try:
        face = db.faces.get_face_by_id(face_id)
        if not face:
            return jsonify({"error": "Face not found"}), 404

        photo = db.photos.get_photo_by_id(face["photo_id"])
        if not photo:
            return jsonify({"error": "Photo not found"}), 404

        file_path = photo.get("file_path", "")
        if not file_path or not os.path.exists(file_path):
            return jsonify({"error": "Image file not found"}), 404
        if not is_allowed_photo_path(file_path):
            return jsonify({"error": "Photo path is outside allowed photo roots"}), 403

        img = cv2.imread(file_path)
        if img is None:
            return jsonify({"error": "Could not read image"}), 500

        h, w = img.shape[:2]
        x0, y0, x1, y1 = face["bbox"]

        # Add 20% padding around the face
        pad_x = int((x1 - x0) * 0.20)
        pad_y = int((y1 - y0) * 0.20)
        x0 = max(0, x0 - pad_x)
        y0 = max(0, y0 - pad_y)
        x1 = min(w, x1 + pad_x)
        y1 = min(h, y1 + pad_y)

        cropped = img[y0:y1, x0:x1]

        # Resize to fixed thumbnail size
        thumb = cv2.resize(cropped, (128, 128), interpolation=cv2.INTER_LANCZOS4)

        # Encode to JPEG bytes
        _, buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return send_file(
            io.BytesIO(buf.tobytes()),
            mimetype="image/jpeg",
            max_age=3600,
        )

    except Exception as e:
        logger.error(f"face-crop error for face {face_id}: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/players/<int:cluster_id>/faces/<int:face_id>", methods=["DELETE"])
def remove_face_from_cluster(cluster_id: int, face_id: int):
    """Remove a face from a player cluster (deselect a photo from tagged group)."""
    db = current_app.db
    try:
        db.faces.deassign_faces([face_id])
        return jsonify({"success": True, "message": f"Removed face {face_id} from cluster {cluster_id}"}), 200
    except Exception as e:
        logger.error(f"Error removing face {face_id} from cluster {cluster_id}: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/consolidate-player/<string:player_name>", methods=["POST"])
def consolidate_player_clusters(player_name: str):
    """Merge all clusters with the same player_name into one primary cluster."""
    db = current_app.db
    try:
        result = db.clusters.consolidate_player_clusters(player_name)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error consolidating clusters for player {player_name}: {e}")
        return jsonify({"error": str(e)}), 500


def _enqueue_job(job_type: str, payload: dict, task):
    """Helper to enqueue an async job."""
    db = current_app.db
    app = current_app
    job_id = app.job_runner.submit(job_type, payload, task)
    job = db.jobs.get_processing_job(job_id)
    return jsonify({"success": True, "job_id": job_id, "job": job}), 202
