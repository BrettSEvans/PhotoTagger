import logging
import os
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory
import requests
from src.db import Database
from src.roster_import import RosterImportError, RosterImporter, parse_roster_file
from src.metadata_sidecar import PhotoMetadata, write_xmp_sidecar

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

    def enqueue_job(job_type: str, payload: dict, task):
        job_id = app.job_runner.submit(job_type, payload, task)
        job = db.get_processing_job(job_id)
        return jsonify({"success": True, "job_id": job_id, "job": job}), 202

    def parse_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def parse_int_arg(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def configured_photo_roots() -> list[Path]:
        raw = os.environ.get("PHOTOTAGGER_ALLOWED_PHOTO_ROOTS", "").strip()
        if not raw:
            return []
        parts = [part.strip() for chunk in raw.split(os.pathsep) for part in chunk.split(",")]
        return [Path(part).expanduser().resolve() for part in parts if part]

    def is_allowed_photo_path(photo_path: str) -> bool:
        path = Path(photo_path).expanduser().resolve()
        if ".git" in path.parts:
            return False
        roots = configured_photo_roots()
        if not roots:
            return True
        return any(path == root or root in path.parents for root in roots)

    def is_allowed_photo_directory(photo_dir: str) -> bool:
        return is_allowed_photo_path(photo_dir)

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
        roster_entry = db.get_roster_entry_by_id(roster_entry_id)
        if not roster_entry:
            return {
                "requested": True,
                "written": 0,
                "skipped": len(face_ids),
                "failed": 0,
                "opponent_omitted": True,
                "errors": ["Roster entry not found"],
            }

        context = db.get_game_context()
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

    # Health check endpoint
    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        return jsonify({"status": "ok", "mode": get_runtime_mode()}), 200

    @app.route("/api/app-config", methods=["GET"])
    def app_config():
        return jsonify({
            "mode": get_runtime_mode(),
            "local_agent_default_url": "http://127.0.0.1:5001",
            "requires_agent_token": bool(os.environ.get("PHOTOTAGGER_AGENT_TOKEN")),
        }), 200

    # Search photos by jersey number
    @app.route("/api/search", methods=["GET"])
    def search():
        """
        Search for photos by jersey number with optional filters.

        Query params:
        - jersey: Jersey number (required)
        - min_confidence: Minimum OCR confidence (0-1, optional, default 0)
        - team: Team name for roster lookup (optional)
        - year: Team year for roster lookup (optional)

        Returns:
            JSON with matching photos and player names (if roster provided)
        """
        jersey = request.args.get("jersey", "").strip()
        min_confidence = parse_float(request.args.get("min_confidence", "0.0"))
        team = request.args.get("team", "").strip()
        year = request.args.get("year", "").strip()

        if not jersey:
            return jsonify({"error": "jersey parameter required"}), 400
        if min_confidence is None:
            return jsonify({"error": "min_confidence must be a number"}), 400

        # Get raw results
        all_results = db.get_photo_by_jersey(jersey)

        # Filter by confidence
        results = [r for r in all_results if r["confidence"] >= min_confidence]

        # Add assigned player names from cluster assignments
        for result in results:
            assigned_name = db.get_assigned_player_for_photo(result["id"])
            if assigned_name:
                result["player_name"] = assigned_name
            elif team and year:
                # Fallback to roster lookup if no cluster assignment
                try:
                    year_int = int(year)
                    if hasattr(app, 'roster_manager'):
                        player_name = app.roster_manager.get_player_name(team, year_int, jersey)
                        result["player_name"] = player_name
                except (ValueError, AttributeError):
                    pass

        return jsonify({
            "jersey": jersey,
            "count": len(results),
            "min_confidence": min_confidence,
            "results": results,
        }), 200

    # Crawl photos endpoint
    @app.route("/api/crawl", methods=["POST"])
    def crawl():
        """
        Crawl a local photo directory and ingest photos.

        JSON body:
        {
            "photo_dir": "/path/to/photos",
            "team_name": "Team A",  // optional
            "team_year": 2026,       // optional
            "tournament": "Regional" // optional
        }
        """
        data = request.get_json() or {}
        photo_dir = data.get("photo_dir", "./photos")

        if not isinstance(photo_dir, str) or not photo_dir.strip():
            return jsonify({"error": "photo_dir is required"}), 400

        photo_dir = os.path.abspath(os.path.expanduser(photo_dir.strip()))

        if not is_allowed_photo_directory(photo_dir):
            return jsonify({"error": "photo_dir is not an allowed photo directory"}), 400

        if not os.path.isdir(photo_dir):
            return jsonify({"error": f"Directory not found: {photo_dir}"}), 404

        try:
            # Create batch for this import
            batch_id = db.create_batch(
                source_folder=photo_dir,
                team_name=data.get("team_name"),
                team_year=data.get("team_year"),
                tournament=data.get("tournament"),
            )

            def crawl_with_batch():
                result = app.crawler.crawl(photo_dir, batch_id=batch_id)
                # Update batch photo count
                db.update_batch_photo_count(batch_id)
                return result

            return enqueue_job("crawl", {"photo_dir": photo_dir, "batch_id": batch_id}, crawl_with_batch)
        except Exception as e:
            logger.error(f"Crawl error: {e}")
            return jsonify({"error": str(e)}), 500

    # Process OCR endpoint
    @app.route("/api/process-ocr", methods=["POST"])
    def process_ocr():
        """
        Process OCR on photos in the database.

        JSON body (optional):
        {
            "photo_ids": [1, 2, 3]  // Optional: process specific photos
        }
        """
        data = request.get_json() or {}
        photo_ids = data.get("photo_ids", None)

        try:
            return enqueue_job("process_ocr", {"photo_ids": photo_ids}, lambda: app.ocr_engine.process_batch(photo_ids))
        except Exception as e:
            logger.error(f"OCR error: {e}")
            return jsonify({"error": str(e)}), 500

    # Info endpoint
    @app.route("/api/info", methods=["GET"])
    def info():
        """Get database statistics."""
        all_photos = db.get_all_photos()

        return jsonify({
            "total_photos": len(all_photos),
            "db_path": db.db_path,
        }), 200

    @app.route("/api/jobs/<int:job_id>", methods=["GET"])
    def get_job(job_id: int):
        """Get processing job status."""
        job = db.get_processing_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        return jsonify({"job": job}), 200

    # Get face data endpoint
    @app.route("/api/faces/<int:photo_id>", methods=["GET"])
    def get_faces(photo_id):
        """Get all detected faces for a photo."""
        try:
            faces = db.get_faces_by_photo(photo_id)
            return jsonify({
                "photo_id": photo_id,
                "face_count": len(faces),
                "faces": [
                    {
                        "id": f["id"],
                        "bbox": f["bbox"],
                        "confidence": f["confidence"],
                        "embedding_dim": len(f["embedding"])
                    }
                    for f in faces
                ]
            }), 200
        except Exception as e:
            logger.error(f"Error getting faces for photo {photo_id}: {e}")
            return jsonify({"error": str(e)}), 500

    # Native OS directory picker endpoint
    @app.route("/api/pick-directory", methods=["POST"])
    def pick_directory():
        """Open native macOS directory picker via AppleScript and return selected path."""
        try:
            import subprocess
            result = subprocess.run(
                [
                    "osascript", "-e",
                    'POSIX path of (choose folder with prompt "Select Photo Directory")'
                ],
                capture_output=True,
                text=True,
                timeout=120,   # 2 min for user to pick a folder
            )
            if result.returncode == 0:
                path = result.stdout.strip().rstrip("/")
                return jsonify({"path": path, "cancelled": False}), 200
            else:
                # User hit Cancel (osascript exits non-zero)
                return jsonify({"path": None, "cancelled": True}), 200
        except subprocess.TimeoutExpired:
            return jsonify({"path": None, "cancelled": True}), 200
        except Exception as e:
            logger.error(f"Error opening directory picker: {e}")
            return jsonify({"error": str(e)}), 500

    # Get all photos endpoint
    @app.route("/api/photos", methods=["GET"])
    def get_photos():
        """Get all photos in database."""
        try:
            page = parse_int_arg(request.args.get("page", "1"))
            per_page = parse_int_arg(request.args.get("per_page", "20"))

            if page is None:
                return jsonify({"error": "page must be an integer"}), 400
            if per_page is None:
                return jsonify({"error": "per_page must be an integer"}), 400

            # Validate pagination parameters
            if page < 1 or per_page < 1:
                return jsonify({"error": "page and per_page must be >= 1"}), 400
            if per_page > 100:
                per_page = 100  # Cap maximum per_page to prevent abuse

            all_photos = db.get_all_photos()

            # Simple pagination
            start = (page - 1) * per_page
            end = start + per_page
            paginated = all_photos[start:end]

            return jsonify({
                "photos": [
                    {
                        "id": p.get("id"),
                        "filename": os.path.basename(p.get("file_path", "")) if p.get("file_path") else "Unknown",
                        "path": p.get("file_path", ""),
                        "added_at": p.get("ingested_at", ""),
                    }
                    for p in paginated
                ],
                "total": len(all_photos),
                "page": page,
                "per_page": per_page,
            }), 200
        except Exception as e:
            logger.error(f"Error getting photos: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return jsonify({"error": str(e)}), 500

    # Serve image file by photo ID
    @app.route("/api/image/<int:photo_id>", methods=["GET"])
    def serve_image(photo_id: int):
        """Serve an image file from disk by its database ID."""
        try:
            photo = db.get_photo_by_id(photo_id)
            if not photo:
                return jsonify({"error": "Photo not found"}), 404

            file_path = photo.get("file_path", "")
            if not file_path or not os.path.exists(file_path):
                return jsonify({"error": "File not found on disk"}), 404
            if not is_allowed_photo_path(file_path):
                return jsonify({"error": "Image path is outside allowed photo roots"}), 403

            directory = os.path.dirname(os.path.abspath(file_path))
            filename = os.path.basename(file_path)
            return send_from_directory(directory, filename)
        except Exception as e:
            logger.error(f"Error serving image {photo_id}: {e}")
            return jsonify({"error": str(e)}), 500

    # Detect faces endpoint — runs InsightFace on all (or specified) photos
    @app.route("/api/detect-faces", methods=["POST"])
    def detect_faces_endpoint():
        """
        Run face detection on all photos and store embeddings.

        JSON body (optional):
        {
            "photo_ids": [1, 2, 3]  // Optional: process specific photos
        }
        """
        from src.face_detector import FaceDetector
        import json as _json

        data = request.get_json() or {}
        photo_ids = data.get("photo_ids", None)

        try:
            def run_detection():
                detector = FaceDetector()
                photos = db.get_all_photos()

                if photo_ids:
                    photos = [p for p in photos if p["id"] in set(photo_ids)]

                total_faces = 0
                errors = 0
                skipped_existing = 0

                for photo in photos:
                    photo_id = photo["id"]
                    file_path = photo.get("file_path", "")
                    if not file_path or not os.path.exists(file_path):
                        continue
                    if db.photo_has_faces(photo_id):
                        skipped_existing += 1
                        continue
                    try:
                        faces = detector.detect_faces(file_path)
                        for face in faces:
                            emb_list = face["embedding"].tolist() if hasattr(face["embedding"], "tolist") else face["embedding"]
                            db.add_face(
                                photo_id=photo_id,
                                embedding=emb_list,
                                bbox=face["bbox"],
                                confidence=face["confidence"],
                            )
                        total_faces += len(faces)
                    except Exception as e:
                        logger.error(f"Face detection error on photo {photo_id}: {e}")
                        errors += 1

                return {
                    "photos_processed": len(photos),
                    "faces_detected": total_faces,
                    "photos_skipped_existing": skipped_existing,
                    "errors": errors,
                }

            return enqueue_job("detect_faces", {"photo_ids": photo_ids}, run_detection)

        except Exception as e:
            logger.error(f"detect-faces error: {e}")
            return jsonify({"error": str(e)}), 500

    # Cluster players endpoint — group stored faces into player identities
    @app.route("/api/cluster-players", methods=["POST"])
    def cluster_players():
        """Cluster all detected faces into player identities."""
        from src.face_cluster import FaceClusterer

        data = request.get_json() or {}
        threshold = parse_float(data.get("threshold", 0.40))
        if threshold is None:
            return jsonify({"error": "threshold must be a number"}), 400

        try:
            def run_clustering():
                clusterer = FaceClusterer(db, similarity_threshold=threshold)
                return clusterer.run()

            return enqueue_job("cluster_players", {"threshold": threshold}, run_clustering)
        except Exception as e:
            logger.error(f"cluster-players error: {e}")
            return jsonify({"error": str(e)}), 500

    # Get all player clusters
    @app.route("/api/players", methods=["GET"])
    def get_players():
        """Get all player clusters with stats."""
        try:
            clusters = db.get_all_player_clusters()
            return jsonify({
                "players": clusters,
                "total": len(clusters),
            }), 200
        except Exception as e:
            logger.error(f"get-players error: {e}")
            return jsonify({"error": str(e)}), 500

    # Get photos for a specific player cluster
    @app.route("/api/players/<int:cluster_id>/photos", methods=["GET"])
    def get_player_photos(cluster_id: int):
        """Get all photos containing a specific player."""
        min_face_confidence = parse_float(request.args.get("min_face_confidence", "0.0"))
        if min_face_confidence is None:
            return jsonify({"error": "min_face_confidence must be a number"}), 400

        try:
            photos = db.get_photos_by_cluster(cluster_id, min_face_confidence)
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

    # Serve cropped face image
    @app.route("/api/face-crop/<int:face_id>", methods=["GET"])
    def serve_face_crop(face_id: int):
        """Serve a cropped face image (with padding) as JPEG."""
        import io
        try:
            import cv2
            import numpy as np

            face = db.get_face_by_id(face_id)
            if not face:
                return jsonify({"error": "Face not found"}), 404

            photo = db.get_photo_by_id(face["photo_id"])
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

    # ── Roster endpoints ─────────────────────────────────────────────────────────

    @app.route("/api/roster", methods=["GET"])
    def get_roster():
        try:
            entries = db.get_all_roster_entries()
            return jsonify({"entries": entries, "total": len(entries)}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/game-context", methods=["GET"])
    def get_game_context():
        try:
            teams = db.get_game_context()
            return jsonify({"teams": teams}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/game-context", methods=["PUT"])
    def set_game_context():
        data = request.get_json() or {}
        teams = data.get("teams", [])
        if not isinstance(teams, list):
            return jsonify({"error": "teams must be a list"}), 400

        normalized = []
        for idx, team in enumerate(teams, start=1):
            team_name = str(team.get("team_name", "")).strip() if isinstance(team, dict) else ""
            uniform_color = str(team.get("uniform_color", "")).strip().lower() if isinstance(team, dict) else ""
            try:
                team_year = int(team.get("team_year", 2026)) if isinstance(team, dict) else 2026
            except (TypeError, ValueError):
                return jsonify({"error": f"teams[{idx}].team_year must be an integer"}), 400
            if not team_name or not uniform_color:
                return jsonify({"error": f"teams[{idx}] requires team_name and uniform_color"}), 400
            normalized.append({
                "team_name": team_name,
                "team_year": team_year,
                "uniform_color": uniform_color,
            })

        try:
            db.set_game_context(normalized)
            return jsonify({"success": True, "teams": db.get_game_context()}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/roster", methods=["POST"])
    def add_roster():
        data = request.get_json() or {}
        jersey = str(data.get("jersey_number", "")).strip()
        name   = str(data.get("player_name", "")).strip()
        team   = str(data.get("team_name", "Manual Entry")).strip()
        try:
            year = int(data.get("team_year", 2026))
        except (TypeError, ValueError):
            return jsonify({"error": "team_year must be an integer"}), 400
        uniform_color = str(data.get("uniform_color", "")).strip().lower() or None
        if not jersey or not name:
            return jsonify({"error": "jersey_number and player_name are required"}), 400
        try:
            db.add_roster_entry(team, year, jersey, name, uniform_color=uniform_color)
            return jsonify({"success": True}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/roster/infer", methods=["POST"])
    def infer_team_and_year():
        """Infer team name and year from a roster filename.

        JSON body:
        {
            "filename": "Carleton CUT 2026.csv"
        }

        Returns:
        {
            "team_name": "Carleton CUT" or null,
            "team_year": 2026 or null
        }
        """
        data = request.get_json() or {}
        filename = data.get("filename", "").strip()
        if not filename:
            return jsonify({"error": "filename is required"}), 400

        from src.roster_import import infer_team_and_year
        team, year = infer_team_and_year(filename)
        return jsonify({
            "team_name": team,
            "team_year": year,
        }), 200

    @app.route("/api/roster/import", methods=["POST"])
    def import_roster_file():
        team = str(request.form.get("team_name", "Manual Entry")).strip() or "Manual Entry"
        uniform_color = str(request.form.get("uniform_color", "")).strip().lower() or None
        try:
            year = int(request.form.get("team_year", 2026))
        except (TypeError, ValueError):
            return jsonify({"error": "team_year must be an integer"}), 400

        duplicate_policy = str(request.form.get("duplicate_policy", "replace")).strip()
        if duplicate_policy not in {"replace", "skip"}:
            return jsonify({"error": "duplicate_policy must be 'replace' or 'skip'"}), 400

        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename:
            return jsonify({"error": "file is required"}), 400

        try:
            rows = parse_roster_file(uploaded.filename, uploaded.read())
            result = db.import_roster_entries(team, year, rows, duplicate_policy, uniform_color=uniform_color)
            return jsonify(result), 200
        except RosterImportError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            logger.error(f"roster file import error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/roster/infer-url", methods=["POST"])
    def infer_roster_url():
        """Infer team name and year from a roster URL (USA Ultimate pages).

        JSON body:
        {
            "url": "https://play.usaultimate.org/teams/events/Eventteam/?TeamId=..."
        }

        Returns:
        {
            "team_name": "Carleton CUT" or null,
            "team_year": 2026 or null
        }
        """
        data = request.get_json() or {}
        url = str(data.get("url", "")).strip()
        if not url:
            return jsonify({"error": "url is required"}), 400

        try:
            from src.roster_import import extract_team_and_year_from_html
            # Fetch the HTML to extract metadata
            response = requests.get(url, timeout=20, headers={"User-Agent": "PhotoTagger roster importer"})
            response.raise_for_status()
            team, year = extract_team_and_year_from_html(response.text)
            return jsonify({
                "team_name": team,
                "team_year": year,
            }), 200
        except Exception as e:
            logger.warning(f"Could not infer team/year from URL: {e}")
            return jsonify({"team_name": None, "team_year": None}), 200

    @app.route("/api/roster/import-url", methods=["POST"])
    def import_roster_url():
        data = request.get_json() or {}
        url = str(data.get("url", "")).strip()
        team = str(data.get("team_name", "Manual Entry")).strip() or "Manual Entry"
        uniform_color = str(data.get("uniform_color", "")).strip().lower() or None
        duplicate_policy = str(data.get("duplicate_policy", "replace")).strip()

        if not url:
            return jsonify({"error": "url is required"}), 400
        try:
            year = int(data.get("team_year", 2026))
        except (TypeError, ValueError):
            return jsonify({"error": "team_year must be an integer"}), 400
        if duplicate_policy not in {"replace", "skip"}:
            return jsonify({"error": "duplicate_policy must be 'replace' or 'skip'"}), 400

        try:
            rows = RosterImporter.fetch_url(url)
            result = db.import_roster_entries(team, year, rows, duplicate_policy, uniform_color=uniform_color)
            return jsonify(result), 200
        except RosterImportError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            logger.error(f"roster URL import error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/roster/<int:entry_id>", methods=["DELETE"])
    def delete_roster(entry_id: int):
        try:
            db.delete_roster_entry(entry_id)
            return jsonify({"success": True}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/roster/<int:entry_id>", methods=["PUT"])
    def update_roster(entry_id: int):
        """Update a roster entry with any combination of fields.

        JSON body (all fields optional):
        {
            "player_name": "New Name",
            "jersey_number": "23",
            "team_name": "New Team",
            "team_year": 2026,
            "uniform_color": "blue"
        }

        Returns: Updated roster entry or error
        """
        data = request.get_json() or {}
        try:
            # Extract and validate optional fields
            updates = {}

            if "player_name" in data:
                updates["player_name"] = str(data["player_name"]).strip()
            if "jersey_number" in data:
                updates["jersey_number"] = str(data["jersey_number"]).strip()
            if "team_name" in data:
                updates["team_name"] = str(data["team_name"]).strip()
            if "team_year" in data:
                updates["team_year"] = int(data["team_year"])
            if "uniform_color" in data:
                updates["uniform_color"] = str(data["uniform_color"]).strip() if data["uniform_color"] else None

            # Call database update
            updated_entry = db.update_roster_entry(entry_id, **updates)
            return jsonify(updated_entry), 200

        except ValueError as e:
            # Validation errors (unique constraint, empty fields, etc.)
            return jsonify({"error": str(e)}), 409
        except Exception as e:
            logger.exception(f"Error updating roster entry {entry_id}: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/roster/search", methods=["GET"])
    def search_roster():
        q = request.args.get("q", "").strip()
        if not q:
            return jsonify({"results": []}), 200
        try:
            results = db.search_roster(q)
            return jsonify({"results": results}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Photo Batch (Import Group) Management ────────────────────────────────

    @app.route("/api/batches", methods=["GET"])
    def list_batches():
        """List all photo batches."""
        try:
            batches = db.get_all_batches()
            return jsonify({"batches": batches}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/batches/<int:batch_id>", methods=["GET"])
    def get_batch(batch_id: int):
        """Get a single batch by ID."""
        try:
            batch = db.get_batch(batch_id)
            if not batch:
                return jsonify({"error": "Batch not found"}), 404
            photos = db.get_photos_by_batch(batch_id)
            return jsonify({"batch": batch, "photos": photos}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/batches/<int:batch_id>", methods=["PUT"])
    def update_batch(batch_id: int):
        """Update batch metadata (team_name, team_year, tournament)."""
        data = request.get_json() or {}
        try:
            db.update_batch(
                batch_id,
                team_name=data.get("team_name"),
                team_year=data.get("team_year"),
                tournament=data.get("tournament"),
            )
            batch = db.get_batch(batch_id)
            return jsonify({"success": True, "batch": batch}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/batches/<int:batch_id>", methods=["DELETE"])
    def delete_batch(batch_id: int):
        """Delete a batch (unpin photos from it)."""
        try:
            affected = db.delete_batch(batch_id)
            return jsonify({"success": True, "affected_photos": affected}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Processing summary & review endpoints ─────────────────────────────────

    @app.route("/api/processing-summary", methods=["GET"])
    def processing_summary():
        try:
            summary = db.get_processing_summary()
            return jsonify(summary), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/confirmed-photos", methods=["GET"])
    def confirmed_photos():
        limit  = parse_int_arg(request.args.get("limit", 60))
        offset = parse_int_arg(request.args.get("offset", 0))
        if limit is None or offset is None:
            return jsonify({"error": "limit and offset must be integers"}), 400
        try:
            photos = db.get_confirmed_photos(limit, offset)
            return jsonify({"photos": photos, "total": len(photos)}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/review-photos", methods=["GET"])
    def review_photos():
        limit  = parse_int_arg(request.args.get("limit", 60))
        offset = parse_int_arg(request.args.get("offset", 0))
        if limit is None or offset is None:
            return jsonify({"error": "limit and offset must be integers"}), 400
        try:
            photos = db.get_review_photos(limit, offset)
            return jsonify({"photos": photos, "total": len(photos)}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/faces/deassign", methods=["POST"])
    def deassign_faces():
        data = request.get_json() or {}
        face_ids = [int(x) for x in data.get("face_ids", [])]
        try:
            result = db.deassign_faces(face_ids)
            return jsonify({"success": True, **result}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/players/<int:cluster_id>/assign", methods=["POST"])
    def assign_cluster(cluster_id: int):
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
            db.assign_cluster_to_player(cluster_id, player_name, jersey_number, roster_entry_id)
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
                    metadata_result = write_assignment_metadata(cluster_id, roster_entry_id, face_ids)
            return jsonify({"success": True, "metadata": metadata_result}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/players/<int:cluster_id>/match-similar", methods=["POST"])
    def match_similar_clusters(cluster_id: int):
        """Post-assignment similarity scan.

        Compares the centroid of the just-assigned cluster against every
        unidentified cluster's centroid.
        - similarity >= 0.85  → auto-tag with the same player
        - 0.70 <= similarity < 0.85 → return as user suggestions
        """
        import numpy as np

        def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
            na, nb = np.linalg.norm(a), np.linalg.norm(b)
            if na == 0 or nb == 0:
                return 0.0
            return float(np.dot(a, b) / (na * nb))

        try:
            cluster = db.get_cluster_by_id(cluster_id)
            if not cluster or not cluster.get("player_name"):
                return jsonify({"error": "cluster is not assigned to a player"}), 400

            player_name    = cluster["player_name"]
            jersey_number  = cluster["jersey_number"]
            roster_entry_id = cluster["roster_entry_id"]

            # Centroid of the newly-assigned cluster
            assigned_embs = db.get_cluster_face_embeddings(cluster_id)
            if not assigned_embs:
                return jsonify({"auto_tagged": [], "suggestions": []}), 200

            assigned_centroid = np.mean(
                [np.array(e, dtype=np.float32) for e in assigned_embs], axis=0
            )

            auto_tagged: list = []
            suggestions: list = []

            for uc in db.get_unidentified_clusters_with_embeddings():
                if not uc["embeddings"]:
                    continue
                uc_centroid = np.mean(
                    [np.array(e, dtype=np.float32) for e in uc["embeddings"]], axis=0
                )
                sim = _cosine_similarity(assigned_centroid, uc_centroid)

                entry = {
                    "cluster_id":       uc["id"],
                    "face_count":       uc["face_count"],
                    "thumbnail_face_id": uc["thumbnail_face_id"],
                    "similarity":       round(float(sim), 3),
                }

                if sim >= 0.85:
                    db.assign_cluster_to_player(
                        uc["id"], player_name, jersey_number, roster_entry_id
                    )
                    auto_tagged.append({**entry, "player_name": player_name, "jersey_number": jersey_number})
                elif sim >= 0.70:
                    suggestions.append(entry)

            return jsonify({"auto_tagged": auto_tagged, "suggestions": suggestions}), 200

        except Exception as exc:
            logger.exception("match-similar failed for cluster %s", cluster_id)
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/data/reset", methods=["POST"])
    def reset_all_data():
        """Delete every row from all user-data tables.

        Requires { "confirm": true } in the request body as a safety gate.
        """
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

    # Get detection status
    @app.route("/api/detection-status", methods=["GET"])
    def detection_status():
        """Return counts of faces and clusters in DB."""
        try:
            face_count = db.get_face_count()
            clusters = db.get_all_player_clusters()
            return jsonify({
                "face_count": face_count,
                "cluster_count": len(clusters),
            }), 200
        except Exception as e:
            logger.error(f"detection-status error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/", defaults={"asset_path": ""}, methods=["GET"])
    @app.route("/<path:asset_path>", methods=["GET"])
    def serve_cloud_ui(asset_path: str):
        """Serve the built React app when deployed as a Railway cloud UI."""
        if get_runtime_mode() != "cloud-ui":
            return jsonify({"error": "cloud UI is not enabled"}), 404
        dist = Path(__file__).resolve().parents[1] / "web" / "dist"

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

    return app

if __name__ == "__main__":
    app = create_app()
    debug = should_enable_debug()
    host, port = get_server_bind()
    deployment_env = get_deployment_env()
    logger.info(f"Starting PhotoTagger API on http://{host}:{port}")
    logger.info(f"Deployment environment: {deployment_env}")
    app.run(debug=debug, port=port, host=host, use_reloader=False)
