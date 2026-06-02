import io
import logging
import os
import shutil
import tempfile
import traceback
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory
from werkzeug.utils import secure_filename
import numpy as np
import requests
from src.db import Database
from src.roster_import import RosterImportError, RosterImporter, parse_roster_file
from src.metadata_sidecar import PhotoMetadata, write_xmp_sidecar
from src.utils import parse_float, parse_int_arg, configured_photo_roots, is_allowed_photo_path, is_allowed_photo_directory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def should_enable_debug() -> bool:
    """Return whether Flask debug mode should be enabled for local development."""
    return os.environ.get("PHOTOTAGGER_DEBUG", "").lower() in {"1", "true", "yes", "on"}

def get_runtime_mode() -> str:
    return os.environ.get("PHOTOTAGGER_MODE", "local-agent").strip() or "local-agent"

def is_railway_deployment() -> bool:
    """Detect if running on Railway.app by checking for Railway-specific env vars."""
    # Railway sets these environment variables automatically
    railway_env_vars = [
        "RAILWAY_ENVIRONMENT_ID",
        "RAILWAY_SERVICE_ID",
        "RAILWAY_SERVICE_NAME",
        "RAILWAY_PROJECT_ID",
    ]
    return any(os.environ.get(var) for var in railway_env_vars)

def get_deployment_env() -> str:
    """Return 'railway' if running on Railway.app, 'local' otherwise."""
    return "railway" if is_railway_deployment() else "local"

def get_server_bind() -> tuple[str, int]:
    """Return host and port for local development or Railway-style hosted runtime."""
    port = int(os.environ.get("PORT", "5001"))
    host = "0.0.0.0" if os.environ.get("PORT") or get_runtime_mode() == "cloud-ui" else "127.0.0.1"
    return host, port

def write_assignment_metadata(db: Database, cluster_id: int, roster_entry_id: int, face_ids: list[int]) -> dict:
    """Write assignment metadata to photo XMP sidecars."""
    roster_entry = db.roster.get_roster_entry_by_id(roster_entry_id)
    if not roster_entry:
        return {
            "requested": True,
            "written": 0,
            "skipped": len(face_ids),
            "failed": 0,
            "opponent_omitted": True,
            "errors": ["Roster entry not found"],
        }

    context = db.context.get_game_context()
    opponents = [
        team for team in context
        if team["team_name"] != roster_entry["team_name"] or int(team["team_year"]) != int(roster_entry["team_year"])
    ]
    opponent_name = opponents[0]["team_name"] if len(opponents) == 1 else None
    photo_rows = db.get_photos_by_face_ids(cluster_id, face_ids)
    found_face_ids = {row["face_id"] for row in photo_rows}
    missing_face_ids = [face_id for face_id in face_ids if face_id not in found_face_ids]
    errors = [f"Face {face_id} is not assigned to cluster {cluster_id}" for face_id in missing_face_ids]
    written = 0
    failed = len(missing_face_ids)

    metadata = PhotoMetadata(
        player_name=roster_entry["player_name"],
        team_name=roster_entry["team_name"],
        team_year=int(roster_entry["team_year"]),
        jersey_number=roster_entry["jersey_number"],
        opponent_name=opponent_name,
    )
    for row in photo_rows:
        if not is_allowed_photo_path(row["file_path"]):
            failed += 1
            errors.append(f"Photo path is outside allowed photo roots: {row['file_path']}")
            continue
        result = write_xmp_sidecar(row["file_path"], metadata)
        if result.written:
            written += 1
        else:
            failed += 1
            errors.append(result.error or f"Could not write metadata for face {row['face_id']}")

    return {
        "requested": True,
        "written": written,
        "skipped": 0,
        "failed": failed,
        "opponent_omitted": opponent_name is None,
        "errors": errors,
    }

def create_app(db_path: str = "photo_catalog.db") -> Flask:
    """Create and configure Flask app."""
    app = Flask(__name__)

    # Initialize database
    db = Database(db_path)
    db.init_schema()
    app.db = db

    # Initialize roster manager
    from src.roster import RosterManager
    app.roster_manager = RosterManager()

    # Initialize local processing components only for the filesystem-capable agent.
    if get_runtime_mode() == "cloud-ui":
        app.crawler = None
        app.ocr_engine = None
        app.job_runner = None
    else:
        from src.crawler import PhotoCrawler
        from src.ocr import OCREngine
        from src.job_runner import LocalJobRunner
        app.crawler = PhotoCrawler(db)
        app.ocr_engine = OCREngine(db)
        app.job_runner = LocalJobRunner(db)

    def enqueue_job(job_type: str, payload: dict, task):
        job_id = app.job_runner.submit(job_type, payload, task)
        job = db.jobs.get_processing_job(job_id)
        return jsonify({"success": True, "job_id": job_id, "job": job}), 202

    def valid_agent_token() -> bool:
        expected = os.environ.get("PHOTOTAGGER_AGENT_TOKEN", "")
        if not expected:
            return True
        provided = request.headers.get("X-PhotoTagger-Agent-Token", "")
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            provided = auth.removeprefix("Bearer ").strip()
        if not provided:
            provided = request.args.get("agent_token", "")
        return provided == expected

    @app.before_request
    def require_local_agent_token():
        if request.method == "OPTIONS":
            return None
        if request.path in {"/health", "/api/app-config"}:
            return None
        if os.environ.get("PHOTOTAGGER_AGENT_TOKEN") and request.path.startswith("/api/") and not valid_agent_token():
            return jsonify({"error": "local agent token required"}), 401
        return None

    def write_assignment_metadata(cluster_id: int, roster_entry_id: int, face_ids: list[int]):
        roster_entry = db.roster.get_roster_entry_by_id(roster_entry_id)
        if not roster_entry:
            return {
                "requested": True,
                "written": 0,
                "skipped": len(face_ids),
                "failed": 0,
                "opponent_omitted": True,
                "errors": ["Roster entry not found"],
            }

        context = db.context.get_game_context()
        opponents = [
            team for team in context
            if team["team_name"] != roster_entry["team_name"] or int(team["team_year"]) != int(roster_entry["team_year"])
        ]
        opponent_name = opponents[0]["team_name"] if len(opponents) == 1 else None
        photo_rows = db.get_photos_by_face_ids(cluster_id, face_ids)
        found_face_ids = {row["face_id"] for row in photo_rows}
        missing_face_ids = [face_id for face_id in face_ids if face_id not in found_face_ids]
        errors = [f"Face {face_id} is not assigned to cluster {cluster_id}" for face_id in missing_face_ids]
        written = 0
        failed = len(missing_face_ids)

        metadata = PhotoMetadata(
            player_name=roster_entry["player_name"],
            team_name=roster_entry["team_name"],
            team_year=int(roster_entry["team_year"]),
            jersey_number=roster_entry["jersey_number"],
            opponent_name=opponent_name,
        )
        for row in photo_rows:
            if not is_allowed_photo_path(row["file_path"]):
                failed += 1
                errors.append(f"Photo path is outside allowed photo roots: {row['file_path']}")
                continue
            result = write_xmp_sidecar(row["file_path"], metadata)
            if result.written:
                written += 1
            else:
                failed += 1
                errors.append(result.error or f"Could not write metadata for face {row['face_id']}")

        return {
            "requested": True,
            "written": written,
            "skipped": 0,
            "failed": failed,
            "opponent_omitted": opponent_name is None,
            "errors": errors,
        }

    # Add CORS support — restrict to an allowlist instead of "*" so arbitrary
    # websites cannot drive the local agent on 127.0.0.1.
    def allowed_cors_origins() -> set[str]:
        raw = os.environ.get("PHOTOTAGGER_ALLOWED_ORIGINS", "").strip()
        if raw:
            return {origin.strip() for origin in raw.split(",") if origin.strip()}
        # Sensible defaults for local development (Vite dev server + preview).
        return {
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        }

    @app.after_request
    def after_request(response):
        origin = request.headers.get("Origin")
        if origin and origin in allowed_cors_origins():
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers.add("Vary", "Origin")
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-PhotoTagger-Agent-Token"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        return response

    # Register blueprints
    from src.blueprints.system import bp as system_bp
    from src.blueprints.batches import bp as batches_bp
    from src.blueprints.roster import bp as roster_bp
    from src.blueprints.photos import bp as photos_bp
    from src.blueprints.detection import bp as detection_bp
    from src.blueprints.review import bp as review_bp
    app.register_blueprint(system_bp)
    app.register_blueprint(batches_bp)
    app.register_blueprint(roster_bp)
    app.register_blueprint(photos_bp)
    app.register_blueprint(detection_bp)
    app.register_blueprint(review_bp)

    return app

if __name__ == "__main__":
    app = create_app()
    debug = should_enable_debug()
    host, port = get_server_bind()
    deployment_env = get_deployment_env()
    logger.info(f"Starting PhotoTagger API on http://{host}:{port}")
    logger.info(f"Deployment environment: {deployment_env}")
    app.run(debug=debug, port=port, host=host, use_reloader=False)
