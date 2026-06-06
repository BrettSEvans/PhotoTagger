"""Review and confirmation workflows for cluster assignments."""

import logging
import os
import numpy as np
from flask import Blueprint, request, jsonify, current_app
from src.utils import parse_int_arg

logger = logging.getLogger(__name__)
bp = Blueprint("review", __name__)


@bp.route("/api/processing-summary", methods=["GET"])
def processing_summary():
    db = current_app.db
    try:
        summary = db.review.get_processing_summary()
        return jsonify(summary), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/confirmed-photos", methods=["GET"])
def confirmed_photos():
    db = current_app.db
    limit  = parse_int_arg(request.args.get("limit", 60))
    offset = parse_int_arg(request.args.get("offset", 0))
    if limit is None or offset is None:
        return jsonify({"error": "limit and offset must be integers"}), 400
    try:
        photos = db.review.get_confirmed_photos(limit, offset)
        return jsonify({"photos": photos, "total": len(photos)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/review-photos", methods=["GET"])
def review_photos():
    db = current_app.db
    limit  = parse_int_arg(request.args.get("limit", 60))
    offset = parse_int_arg(request.args.get("offset", 0))
    if limit is None or offset is None:
        return jsonify({"error": "limit and offset must be integers"}), 400
    try:
        photos = db.review.get_review_photos(limit, offset)
        return jsonify({"photos": photos, "total": len(photos)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/faces/deassign", methods=["POST"])
def deassign_faces():
    db = current_app.db
    data = request.get_json() or {}
    face_ids = [int(x) for x in data.get("face_ids", [])]
    try:
        result = db.faces.deassign_faces(face_ids)
        return jsonify({"success": True, **result}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/players/<int:cluster_id>/assign", methods=["POST"])
def assign_cluster(cluster_id: int):
    db = current_app.db
    app = current_app
    data = request.get_json() or {}
    player_name   = str(data.get("player_name", "")).strip()
    jersey_number = str(data.get("jersey_number", "")).strip()
    roster_entry_id = data.get("roster_entry_id", None)
    write_metadata = bool(data.get("write_metadata", False))
    face_ids = [int(face_id) for face_id in data.get("face_ids", [])]
    if roster_entry_id is not None:
        roster_entry_id = int(roster_entry_id)
    if not player_name:
        return jsonify({"error": "player_name is required"}), 400
    try:
        db.clusters.assign_cluster_to_player(cluster_id, player_name, jersey_number, roster_entry_id)
        metadata_result = {
            "requested": False,
            "written": 0,
            "skipped": 0,
            "failed": 0,
            "opponent_omitted": False,
            "errors": [],
        }
        if write_metadata:
            if roster_entry_id is None:
                metadata_result = {
                    "requested": True,
                    "written": 0,
                    "skipped": len(face_ids),
                    "failed": 0,
                    "opponent_omitted": True,
                    "errors": ["roster_entry_id is required to write metadata"],
                }
            else:
                from src.api import write_assignment_metadata
                metadata_result = write_assignment_metadata(db, cluster_id, roster_entry_id, face_ids)
        return jsonify({"success": True, "metadata": metadata_result}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/players/<int:cluster_id>/match-similar", methods=["POST"])
def match_similar_clusters(cluster_id: int):
    """Post-assignment similarity scan.

    Compares the centroid of the just-assigned cluster against every
    unidentified cluster's centroid using InsightFace buffalo_l embeddings
    (512-dim, unnormalized).  Empirical same-person cosine range: ~0.24–0.57
    (mean 0.40, matching the cluster-building threshold of 0.40).

    Thresholds calibrated to this embedding space:
    - similarity >= 0.60  → auto-tag with the same player
    - 0.40 <= similarity < 0.60 → return as user suggestions
    """
    db = current_app.db

    # Calibrated for InsightFace buffalo_l (same-person mean ≈ 0.40,
    # cross-cluster p90 ≈ 0.39, cluster-build threshold = 0.40).
    # AUTO_TAG is set higher (0.60) than the cluster-build threshold so that only
    # very confident matches are applied without user confirmation.
    AUTO_TAG_THRESHOLD = 0.60
    SUGGEST_THRESHOLD  = 0.40

    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    try:
        cluster = db.clusters.get_cluster_by_id(cluster_id)
        if not cluster or not cluster.get("player_name"):
            return jsonify({"error": "cluster is not assigned to a player"}), 400

        player_name    = cluster["player_name"]
        jersey_number  = cluster["jersey_number"]
        roster_entry_id = cluster["roster_entry_id"]

        # Centroid of the newly-assigned cluster
        assigned_embs = db.clusters.get_cluster_face_embeddings(cluster_id)
        if not assigned_embs:
            return jsonify({"auto_tagged": [], "suggestions": []}), 200

        assigned_centroid = np.mean(
            [np.array(e, dtype=np.float32) for e in assigned_embs], axis=0
        )

        auto_tagged: list = []
        suggestions: list = []

        for uc in db.clusters.get_unidentified_clusters_with_embeddings():
            if not uc["embeddings"]:
                continue
            uc_centroid = np.mean(
                [np.array(e, dtype=np.float32) for e in uc["embeddings"]], axis=0
            )
            sim = _cosine_similarity(assigned_centroid, uc_centroid)

            # Get photo_id and face bbox from thumbnail face for modal viewing
            photo_id = None
            face_bbox = None
            if uc["thumbnail_face_id"]:
                loc = db.faces.get_face_photo_location(uc["thumbnail_face_id"])
                if loc:
                    photo_id = loc["photo_id"]
                    face_bbox = loc["face_bbox"]

            entry = {
                "cluster_id":       uc["id"],
                "face_count":       uc["face_count"],
                "thumbnail_face_id": uc["thumbnail_face_id"],
                "photo_id":         photo_id,
                "face_bbox":        face_bbox,
                "similarity":       round(float(sim), 3),
            }

            if sim >= AUTO_TAG_THRESHOLD:
                db.clusters.assign_cluster_to_player(
                    uc["id"], player_name, jersey_number, roster_entry_id
                )
                auto_tagged.append({**entry, "player_name": player_name, "jersey_number": jersey_number})
            elif sim >= SUGGEST_THRESHOLD:
                suggestions.append(entry)

        return jsonify({"auto_tagged": auto_tagged, "suggestions": suggestions}), 200

    except Exception as exc:
        logger.exception("match-similar failed for cluster %s", cluster_id)
        return jsonify({"error": str(exc)}), 500
