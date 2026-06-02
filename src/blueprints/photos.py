"""Photo search, ingestion, and OCR processing endpoints."""

import io
import logging
import os
from pathlib import Path
from flask import Blueprint, request, jsonify, send_file, send_from_directory, current_app
from werkzeug.utils import secure_filename
from src.utils import parse_float, parse_int_arg, configured_photo_roots, is_allowed_photo_path, is_allowed_photo_directory

logger = logging.getLogger(__name__)
bp = Blueprint("photos", __name__)


@bp.route("/api/search", methods=["GET"])
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

    db = current_app.db
    app = current_app

    # Get raw results
    all_results = db.photos.get_photo_by_jersey(jersey)

    # Filter by confidence
    results = [r for r in all_results if r["confidence"] >= min_confidence]

    # Add assigned player names from cluster assignments
    for result in results:
        assigned_name = db.photos.get_assigned_player_for_photo(result["id"])
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


@bp.route("/api/crawl", methods=["POST"])
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
    db = current_app.db
    crawler = current_app.crawler
    app_job_runner = current_app.job_runner

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
        batch_id = db.batches.create_batch(
            source_folder=photo_dir,
            team_name=data.get("team_name"),
            team_year=data.get("team_year"),
            tournament=data.get("tournament"),
        )

        def crawl_with_batch(job_id: int):
            result = crawler.crawl(photo_dir, batch_id=batch_id)
            # Update batch photo count
            db.batches.update_batch_photo_count(batch_id)
            return result

        job_id = app_job_runner.submit("crawl", {"photo_dir": photo_dir, "batch_id": batch_id}, crawl_with_batch)
        job = db.jobs.get_processing_job(job_id)
        return jsonify({"success": True, "job_id": job_id, "job": job}), 202
    except Exception as e:
        logger.error(f"Crawl error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/upload-photos", methods=["POST"])
def upload_photos():
    """
    Handle photo file uploads via multipart form.

    Files are validated first, then stored in a temp directory and processed
    asynchronously.  The temp directory is removed after the job completes
    (success or failure) to prevent disk leaks.
    """
    db = current_app.db
    crawler = current_app.crawler
    app_job_runner = current_app.job_runner

    if 'files' not in request.files:
        return jsonify({"error": "No files provided"}), 400

    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        return jsonify({"error": "No files selected"}), 400

    # Supported image extensions
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.heic', '.webp'}

    try:
        # ── Phase 1: filter to supported image files ──
        # A selected folder commonly contains non-photo files — e.g. a saved web
        # page brings along .gif loaders, .html, .css, .js. Skip anything that
        # isn't a supported image rather than failing the whole upload.
        valid_files = []
        skipped_files = []
        for file in files:
            if not file.filename:
                continue
            ext = Path(file.filename).suffix.lower()
            if ext not in allowed_extensions:
                skipped_files.append(file.filename)
                continue
            valid_files.append(file)

        if skipped_files:
            logger.info(
                f"Skipping {len(skipped_files)} unsupported file(s) in upload "
                f"(e.g. {skipped_files[0]})"
            )

        if not valid_files:
            return jsonify({
                "error": "No supported image files found in the selection",
                "skipped": len(skipped_files),
            }), 400

        # ── Phase 2: save to permanent uploads directory ──
        # Use a permanent directory to avoid deleting photos that are referenced in the database
        uploads_dir = Path("uploads")
        uploads_dir.mkdir(exist_ok=True)

        saved_paths = []
        try:
            for file in valid_files:
                secure_name = secure_filename(file.filename)
                file_path = uploads_dir / secure_name
                file.save(str(file_path))
                saved_paths.append(str(file_path.resolve()))
        except Exception as e:
            logger.error(f"Error saving files to uploads directory: {e}")
            raise

        # Create batch for this import
        batch_id = db.batches.create_batch(
            source_folder=str(uploads_dir.resolve()),
            team_name=request.form.get("team_name"),
            team_year=int(request.form.get("team_year", "0")) or None,
            tournament=request.form.get("tournament"),
        )

        def run_photo_ingestion(job_id: int):
            """Ingest uploaded photo files into the database."""
            photos_ingested = 0
            duplicates_skipped = 0
            errors = 0

            for i, file_path in enumerate(saved_paths):
                try:
                    photo_id = crawler.ingest_single_file(file_path, batch_id=batch_id)
                    if photo_id:
                        photos_ingested += 1
                    else:
                        duplicates_skipped += 1
                except Exception as e:
                    logger.error(f"Error ingesting {file_path}: {e}")
                    errors += 1

                # Update job progress
                progress = int((i + 1) / len(saved_paths) * 100)
                app_job_runner.update_progress(job_id, progress)

            # Update batch photo count
            db.batches.update_batch_photo_count(batch_id)

            return {
                "photos_found": len(saved_paths),
                "photos_ingested": photos_ingested,
                "duplicates_skipped": duplicates_skipped,
                "errors": errors,
            }

        job_id = app_job_runner.submit(
            "upload_photos",
            {
                "file_paths": saved_paths,
                "uploads_dir": str(uploads_dir.resolve()),
                "batch_id": batch_id,
            },
            run_photo_ingestion
        )
        job = db.jobs.get_processing_job(job_id)
        return jsonify({"success": True, "job_id": job_id, "job": job}), 202

    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/process-ocr", methods=["POST"])
def process_ocr():
    """
    Process OCR on photos in the database.

    JSON body (optional):
    {
        "photo_ids": [1, 2, 3]  // Optional: process specific photos
    }
    """
    db = current_app.db
    ocr_engine = current_app.ocr_engine
    app_job_runner = current_app.job_runner

    data = request.get_json() or {}
    photo_ids = data.get("photo_ids", None)

    try:
        def run_ocr(job_id: int):
            return ocr_engine.process_batch(photo_ids)

        job_id = app_job_runner.submit("process_ocr", {"photo_ids": photo_ids}, run_ocr)
        job = db.jobs.get_processing_job(job_id)
        return jsonify({"success": True, "job_id": job_id, "job": job}), 202
    except Exception as e:
        logger.error(f"OCR error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/info", methods=["GET"])
def info():
    """Get database statistics."""
    db = current_app.db
    all_photos = db.photos.get_all_photos()

    return jsonify({
        "total_photos": len(all_photos),
        "db_path": db.db_path,
    }), 200


@bp.route("/api/faces/<int:photo_id>", methods=["GET"])
def get_faces(photo_id):
    """Get all detected faces for a photo."""
    db = current_app.db
    try:
        faces = db.faces.get_faces_by_photo(photo_id)
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


@bp.route("/api/photos", methods=["GET"])
def get_photos():
    """Get all photos in database."""
    db = current_app.db
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

        # Push LIMIT/OFFSET into SQL — never load all rows into memory
        offset = (page - 1) * per_page
        paginated = db.photos.get_all_photos(limit=per_page, offset=offset)
        total = db.photos.count_photos()

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
            "total": total,
            "page": page,
            "per_page": per_page,
        }), 200
    except Exception as e:
        logger.error(f"Error getting photos: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@bp.route("/api/image/<int:photo_id>", methods=["GET"])
def serve_image(photo_id: int):
    """Serve an image file from disk by its database ID."""
    db = current_app.db
    try:
        photo = db.photos.get_photo_by_id(photo_id)
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


def _enqueue_job(job_type: str, payload: dict, task):
    """Helper to enqueue an async job."""
    db = current_app.db
    app = current_app
    job_id = app.job_runner.submit(job_type, payload, task)
    job = db.jobs.get_processing_job(job_id)
    return jsonify({"success": True, "job_id": job_id, "job": job}), 202
