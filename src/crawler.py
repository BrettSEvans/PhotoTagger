import logging
from pathlib import Path
from typing import Dict
from src.db import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PhotoCrawler:
    """Walk a directory tree and ingest photos into the database."""

    # Supported image extensions
    SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}

    def __init__(self, db: Database):
        """Initialize crawler with a database connection."""
        self.db = db

    def crawl(self, photo_dir: str) -> Dict:
        """
        Crawl a directory for photos and ingest them.

        Returns:
            Dict with keys:
            - photos_found: total image files found
            - photos_ingested: successfully added to database
            - duplicates_skipped: already in database
            - errors: number of processing errors
        """
        photo_dir = Path(photo_dir)

        if not photo_dir.exists():
            raise FileNotFoundError(f"Directory not found: {photo_dir}")

        results = {
            "photos_found": 0,
            "photos_ingested": 0,
            "duplicates_skipped": 0,
            "errors": 0,
        }

        # Walk the directory recursively (case-insensitive)
        image_files = []
        for ext in self.SUPPORTED_FORMATS:
            image_files.extend(photo_dir.rglob(f"*{ext}"))
            image_files.extend(photo_dir.rglob(f"*{ext.upper()}"))

        results["photos_found"] = len(image_files)
        logger.info(f"Found {results['photos_found']} image files in {photo_dir}")

        for file_path in image_files:
            try:
                # Compute file hash to detect duplicates
                file_hash = Database._compute_file_hash(str(file_path))

                # Skip if already in database
                if self.db.photo_exists(file_hash):
                    logger.debug(f"Skipping duplicate: {file_path}")
                    results["duplicates_skipped"] += 1
                    continue

                # Ingest the photo
                photo_id = self.db.add_photo(str(file_path), file_hash)
                logger.debug(f"Ingested: {file_path} (ID: {photo_id})")
                results["photos_ingested"] += 1

            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
                results["errors"] += 1

        logger.info(f"Crawl complete: {results}")
        return results
