import logging
from pathlib import Path
from typing import Dict, Optional
from src.db import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PhotoCrawler:
    """Walk a directory tree and ingest photos into the database."""

    # Supported image extensions
    SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".heic", ".webp"}

    def __init__(self, db: Database):
        """Initialize crawler with a database connection."""
        self.db = db

    def crawl(self, photo_dir: str, batch_id: int | None = None) -> Dict:
        """
        Crawl a directory for photos and ingest them.

        Args:
            photo_dir: Directory path to crawl
            batch_id: Optional batch ID to assign photos to

        Returns:
            Dict with keys:
            - photos_found: total image files found
            - photos_ingested: successfully added to database
            - duplicates_skipped: already in database
            - errors: number of processing errors
            - source_folder: the crawled folder path
            - batch_id: the batch ID (if created or provided)
        """
        photo_dir = Path(photo_dir)

        if not photo_dir.exists():
            raise FileNotFoundError(f"Directory not found: {photo_dir}")

        results = {
            "photos_found": 0,
            "photos_ingested": 0,
            "duplicates_skipped": 0,
            "errors": 0,
            "source_folder": str(photo_dir.resolve()),
            "batch_id": batch_id,
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

                # Ingest the photo with source folder and batch
                photo_id = self.db.add_photo(
                    str(file_path),
                    file_hash,
                    source_folder=str(photo_dir.resolve()),
                    batch_id=batch_id,
                )
                logger.debug(f"Ingested: {file_path} (ID: {photo_id})")
                results["photos_ingested"] += 1

            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
                results["errors"] += 1

        logger.info(f"Crawl complete: {results}")
        return results

    def ingest_single_file(self, file_path: str, batch_id: int | None = None) -> Optional[int]:
        """
        Ingest a single uploaded photo file.

        Args:
            file_path: Path to the file to ingest
            batch_id: Optional batch ID to assign the photo to

        Returns:
            photo_id if successfully ingested and not a duplicate, None if duplicate

        Raises:
            FileNotFoundError: if file does not exist
            ValueError: if file format is not supported
        """
        path = Path(file_path)

        # Validate file exists
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Validate file format
        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported file format: {ext}")

        # Compute file hash for duplicate detection
        file_hash = Database._compute_file_hash(str(path))

        # Check for duplicate
        if self.db.photo_exists(file_hash):
            logger.info(f"Duplicate detected: {path.name} (hash: {file_hash})")
            return None

        # Add photo to database
        file_size = path.stat().st_size
        photo_id = self.db.add_photo(
            file_path=str(path.resolve()),
            file_hash=file_hash,
            source_folder=None,
            batch_id=batch_id,
        )

        logger.info(f"Ingested file: {path.name} (ID: {photo_id})")
        return photo_id
