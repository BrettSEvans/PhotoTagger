import logging
import os
from flask import Flask, request, jsonify
from src.db import Database
from src.crawler import PhotoCrawler
from src.ocr import OCREngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app(db_path: str = "photo_catalog.db") -> Flask:
    """Create and configure Flask app."""
    app = Flask(__name__)

    # Initialize database
    db = Database(db_path)
    db.init_schema()
    app.db = db

    # Initialize components
    crawler = PhotoCrawler(db)
    ocr_engine = OCREngine(db)

    # Health check endpoint
    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        return jsonify({"status": "ok"}), 200

    # Search photos by jersey number
    @app.route("/api/search", methods=["GET"])
    def search():
        """
        Search for photos by jersey number.

        Query params:
        - jersey: Jersey number to search for (required)

        Returns:
            JSON with matching photos
        """
        jersey = request.args.get("jersey", "").strip()

        if not jersey:
            return jsonify({"error": "jersey parameter required"}), 400

        results = db.get_photo_by_jersey(jersey)

        return jsonify({
            "jersey": jersey,
            "count": len(results),
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
            results = crawler.crawl(photo_dir)
            return jsonify({
                "success": True,
                "results": results,
            }), 200
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
            results = ocr_engine.process_batch(photo_ids)
            return jsonify({
                "success": True,
                "results": results,
            }), 200
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

    return app

if __name__ == "__main__":
    app = create_app()
    logger.info("Starting PhotoTagger API on http://localhost:5000")
    app.run(debug=True, port=5000)
