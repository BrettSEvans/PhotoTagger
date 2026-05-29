import logging
import os
from flask import Flask, request, jsonify, send_file, send_from_directory
from src.db import Database
from src.crawler import PhotoCrawler
from src.ocr import OCREngine
from src.roster_import import RosterImportError, RosterImporter, parse_roster_file
from src.job_runner import LocalJobRunner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

    # Initialize components
    app.crawler = PhotoCrawler(db)
    app.ocr_engine = OCREngine(db)
    app.job_runner = LocalJobRunner(db)

    def enqueue_job(job_type: str, payload: dict, task):
        job_id = app.job_runner.submit(job_type, payload, task)
        job = db.get_processing_job(job_id)
        return jsonify({"success": True, "job_id": job_id, "job": job}), 202

    # Health check endpoint
    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        return jsonify({"status": "ok"}), 200

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
        min_confidence = float(request.args.get("min_confidence", "0.0"))
        team = request.args.get("team", "").strip()
        year = request.args.get("year", "").strip()

        if not jersey:
            return jsonify({"error": "jersey parameter required"}), 400

        # Get raw results
        all_results = db.get_photo_by_jersey(jersey)

        # Filter by confidence
        results = [r for r in all_results if r["confidence"] >= min_confidence]

        # Add player names if roster available
        if team and year:
            try:
                year_int = int(year)
                for result in results:
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
            "photo_dir": "/path/to/photos"
        }
        """
        data = request.get_json() or {}
        photo_dir = data.get("photo_dir", "./photos")

        if not os.path.isdir(photo_dir):
            return jsonify({"error": f"Directory not found: {photo_dir}"}), 404

        try:
            return enqueue_job("crawl", {"photo_dir": photo_dir}, lambda: app.crawler.crawl(photo_dir))
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
            page = int(request.args.get("page", "1"))
            per_page = int(request.args.get("per_page", "20"))

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

                for photo in photos:
                    photo_id = photo["id"]
                    file_path = photo.get("file_path", "")
                    if not file_path or not os.path.exists(file_path):
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
        threshold = float(data.get("threshold", 0.40))

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
        try:
            photos = db.get_photos_by_cluster(cluster_id)
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

    @app.route("/api/roster", methods=["POST"])
    def add_roster():
        data = request.get_json() or {}
        jersey = str(data.get("jersey_number", "")).strip()
        name   = str(data.get("player_name", "")).strip()
        team   = str(data.get("team_name", "Manual Entry")).strip()
        year   = int(data.get("team_year", 2026))
        if not jersey or not name:
            return jsonify({"error": "jersey_number and player_name are required"}), 400
        try:
            db.add_roster_entry(team, year, jersey, name)
            return jsonify({"success": True}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/roster/import", methods=["POST"])
    def import_roster_file():
        team = str(request.form.get("team_name", "Manual Entry")).strip() or "Manual Entry"
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
            result = db.import_roster_entries(team, year, rows, duplicate_policy)
            return jsonify(result), 200
        except RosterImportError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            logger.error(f"roster file import error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/roster/import-url", methods=["POST"])
    def import_roster_url():
        data = request.get_json() or {}
        url = str(data.get("url", "")).strip()
        team = str(data.get("team_name", "Manual Entry")).strip() or "Manual Entry"
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
            result = db.import_roster_entries(team, year, rows, duplicate_policy)
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
        limit  = int(request.args.get("limit", 60))
        offset = int(request.args.get("offset", 0))
        try:
            photos = db.get_confirmed_photos(limit, offset)
            return jsonify({"photos": photos, "total": len(photos)}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/review-photos", methods=["GET"])
    def review_photos():
        limit  = int(request.args.get("limit", 60))
        offset = int(request.args.get("offset", 0))
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
        if roster_entry_id is not None:
            roster_entry_id = int(roster_entry_id)
        if not player_name:
            return jsonify({"error": "player_name is required"}), 400
        try:
            db.assign_cluster_to_player(cluster_id, player_name, jersey_number, roster_entry_id)
            return jsonify({"success": True}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

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

    # Add CORS support
    @app.after_request
    def after_request(response):
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        return response

    return app

if __name__ == "__main__":
    app = create_app()
    logger.info("Starting PhotoTagger API on http://localhost:5001")
    app.run(debug=True, port=5001, host='127.0.0.1', use_reloader=False)
