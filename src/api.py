import collections
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
from src.utils import parse_float, parse_int_arg, configured_photo_roots, is_allowed_photo_path, is_allowed_photo_directory

# ── In-memory ring-buffer log handler (last 3000 lines) ──────────────────────
# Captured by GET /logs so Claude (and operators) can read live logs without
# SSH access.  No UI link is exposed to end-users.

_LOG_MAX_LINES = 3000

class _RingBufferHandler(logging.Handler):
    """Thread-safe deque-backed handler — oldest lines drop off automatically."""
    def __init__(self, maxlines: int = _LOG_MAX_LINES):
        super().__init__()
        self._buf: collections.deque[str] = collections.deque(maxlen=maxlines)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._buf.append(self.format(record))
        except Exception:
            self.handleError(record)

    def get_lines(self) -> list[str]:
        return list(self._buf)


# Singleton — imported by system.py blueprint for the /logs endpoint
ring_log = _RingBufferHandler()
ring_log.setFormatter(logging.Formatter(
    "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
))
logging.getLogger().addHandler(ring_log)   # attach to root → captures everything

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

        # One-time backup of uploads/ before any IPTC embed can ever run —
        # dispatched as an async job (not run inline in a request handler) so
        # it never blocks the first assign/deassign call. review.py's
        # _embed_names() checks is_backup_ready() and skips the embed
        # (non-fatal) if this hasn't finished yet.
        from src.iptc_writer import backup_directory
        if os.path.isdir("uploads"):
            app.job_runner.submit(
                "backup_uploads",
                {"source": "uploads", "dest": "uploads_backup"},
                lambda job_id: backup_directory("uploads", "uploads_backup"),
            )

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

    # Run OCR self-test once at startup and expose result via /health.
    # This surfaces a dead Tesseract backend immediately rather than silently
    # producing 0 detections for every photo.
    try:
        from src.jersey_recognition import ensure_ocr_ready
        app.config["ocr_ok"] = ensure_ocr_ready()
    except Exception as _ocr_err:
        logger.error(f"OCR startup check failed: {_ocr_err}")
        app.config["ocr_ok"] = False

    return app

if __name__ == "__main__":
    app = create_app()
    debug = should_enable_debug()
    host, port = get_server_bind()
    deployment_env = get_deployment_env()
    logger.info(f"Starting PhotoTagger API on http://{host}:{port}")
    logger.info(f"Deployment environment: {deployment_env}")
    # threaded=True: the dev server must serve the dashboard's concurrent polling
    # (health, roster, summaries, etc.) at the same time as a long multi-file
    # upload. Single-threaded (the Werkzeug default) serializes requests, so a
    # large upload starves polling connections — the browser sees ERR_EMPTY_RESPONSE
    # / ERR_CONNECTION_RESET, surfaced in the UI as "Network Error". The DB layer
    # is thread-safe (single connection, check_same_thread=False, guarded by a lock).
    app.run(debug=debug, port=port, host=host, use_reloader=False, threaded=True)
