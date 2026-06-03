"""Batch management endpoints."""

import logging
from flask import Blueprint, jsonify, request, current_app

logger = logging.getLogger(__name__)

bp = Blueprint("batches", __name__)


@bp.route("/api/batches", methods=["GET"])
def list_batches():
    """List all photo batches."""
    try:
        db = current_app.db
        batches = db.batches.get_all_batches()
        return jsonify({"batches": batches}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/batches/<int:batch_id>", methods=["GET"])
def get_batch(batch_id: int):
    """Get a single batch by ID."""
    try:
        db = current_app.db
        batch = db.batches.get_batch(batch_id)
        if not batch:
            return jsonify({"error": "Batch not found"}), 404
        photos = db.batches.get_photos_by_batch(batch_id)
        return jsonify({"batch": batch, "photos": photos}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/batches/<int:batch_id>", methods=["PUT"])
def update_batch(batch_id: int):
    """Update batch metadata (team_name, team_year, tournament)."""
    data = request.get_json() or {}
    try:
        db = current_app.db
        db.batches.update_batch(
            batch_id,
            team_name=data.get("team_name"),
            team_year=data.get("team_year"),
            tournament=data.get("tournament"),
            name=data.get("name"),
        )
        batch = db.batches.get_batch(batch_id)
        return jsonify({"success": True, "batch": batch}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/batches/<int:batch_id>", methods=["DELETE"])
def delete_batch(batch_id: int):
    """Delete a batch (unpin photos from it)."""
    try:
        db = current_app.db
        affected = db.batches.delete_batch(batch_id)
        return jsonify({"success": True, "affected_photos": affected}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
