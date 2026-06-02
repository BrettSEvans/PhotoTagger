"""System endpoints: health, config, jobs, data reset, cloud UI."""

import logging
import os
from pathlib import Path
from flask import Blueprint, jsonify, current_app, send_from_directory
from src.api import get_runtime_mode

logger = logging.getLogger(__name__)

bp = Blueprint("system", __name__)


@bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "mode": get_runtime_mode()}), 200


@bp.route("/api/app-config", methods=["GET"])
def app_config():
    """Return app configuration."""
    return jsonify({
        "mode": get_runtime_mode(),
        "local_agent_default_url": "http://127.0.0.1:5001",
        "requires_agent_token": bool(os.environ.get("PHOTOTAGGER_AGENT_TOKEN")),
    }), 200


@bp.route("/api/jobs/<int:job_id>", methods=["GET"])
def get_job(job_id: int):
    """Get processing job status."""
    db = current_app.db
    job = db.jobs.get_processing_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"job": job}), 200


@bp.route("/api/detection-status", methods=["GET"])
def detection_status():
    """Return counts of faces and clusters in DB."""
    try:
        db = current_app.db
        face_count = db.faces.get_face_count()
        clusters = db.clusters.get_all_player_clusters()
        return jsonify({
            "face_count": face_count,
            "cluster_count": len(clusters),
        }), 200
    except Exception as e:
        logger.error(f"detection-status error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/data/reset", methods=["POST"])
def reset_data():
    """Delete every row from all user-data tables.

    Requires { "confirm": true } in the request body as a safety gate.
    """
    from flask import request
    db = current_app.db
    data = request.get_json() or {}
    if not data.get("confirm"):
        return jsonify({"error": "confirm field must be true"}), 400
    try:
        deleted = db.reset_all_data()
        logger.info("Database reset: %s", deleted)
        return jsonify({"success": True, "deleted": deleted}), 200
    except Exception as exc:
        logger.exception("reset_all_data failed")
        return jsonify({"error": str(exc)}), 500


@bp.route("/", defaults={"asset_path": ""}, methods=["GET"])
@bp.route("/<path:asset_path>", methods=["GET"])
def serve_cloud_ui(asset_path: str):
    """Serve the built React app when deployed as a Railway cloud UI."""
    if get_runtime_mode() != "cloud-ui":
        return jsonify({"error": "cloud UI is not enabled"}), 404
    dist = Path(__file__).resolve().parents[2] / "web" / "dist"

    # Validate asset_path to prevent directory traversal
    if asset_path:
        try:
            resolved = (dist / asset_path).resolve()
            if not str(resolved).startswith(str(dist.resolve())):
                return jsonify({"error": "invalid asset path"}), 400
            if resolved.is_file():
                return send_from_directory(dist, asset_path)
        except (ValueError, OSError):
            return jsonify({"error": "invalid asset path"}), 400

    index = dist / "index.html"
    if index.is_file():
        return send_from_directory(dist, "index.html")
    return jsonify({"error": "web build not found. Run npm run build in web/ before serving cloud-ui."}), 500
