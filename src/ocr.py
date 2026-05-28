import logging
import re
from typing import List, Optional, Dict
from pathlib import Path
import easyocr
from src.db import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OCREngine:
    """Extract text and jersey numbers from photos using EasyOCR."""

    def __init__(self, db: Database, languages: List[str] = None):
        """
        Initialize OCR engine.

        Args:
            db: Database connection
            languages: Languages to recognize (default: English)
        """
        self.db = db
        self.languages = languages or ["en"]

        # Initialize EasyOCR reader (lazy-loads model on first use)
        logger.info(f"Initializing EasyOCR reader for languages: {self.languages}")
        self.reader = easyocr.Reader(self.languages, gpu=False)

    def process_photo(self, photo_id: int, photo_path: str) -> Optional[Dict]:
        """
        Run OCR on a photo and extract jersey numbers.

        Args:
            photo_id: ID of photo in database
            photo_path: Path to the photo file

        Returns:
            Dict with extracted data or None if processing failed
        """
        try:
            path = Path(photo_path)
            if not path.exists():
                logger.error(f"Photo not found: {photo_path}")
                return None

            # Run OCR
            logger.info(f"Processing photo: {photo_path}")
            results = self.reader.readtext(photo_path)

            # Combine all detected text
            raw_text = " ".join([text for (_, text, _) in results])
            logger.debug(f"Raw OCR text: {raw_text}")

            # Extract jersey numbers
            jerseys = self._extract_jerseys_from_text(raw_text)

            # Store results (pick the first jersey, or None if multiple)
            primary_jersey = jerseys[0] if jerseys else None

            # Calculate confidence as average confidence of all detections
            confidence = sum([conf for (_, _, conf) in results]) / len(results) if results else 0.0

            self.db.add_ocr_result(
                photo_id=photo_id,
                jersey_number=primary_jersey,
                confidence=confidence,
                raw_text=raw_text
            )

            return {
                "photo_id": photo_id,
                "jerseys_found": jerseys,
                "primary_jersey": primary_jersey,
                "confidence": confidence,
                "raw_text": raw_text,
            }

        except Exception as e:
            logger.error(f"Error processing photo {photo_path}: {e}")
            return None

    def process_batch(self, photo_ids: List[int] = None) -> Dict:
        """
        Process all photos in the database (or specific IDs).

        Args:
            photo_ids: Optional list of photo IDs to process. If None, process all.

        Returns:
            Dict with processing statistics
        """
        if photo_ids is None:
            # Process all photos
            photos = self.db.get_all_photos()
            photo_ids = [p["id"] for p in photos]

        results = {
            "photos_processed": 0,
            "jerseys_found": 0,
            "errors": 0,
        }

        for photo_id in photo_ids:
            # Get photo path from database
            photos = self.db.get_all_photos()
            photo = next((p for p in photos if p["id"] == photo_id), None)

            if not photo:
                logger.warning(f"Photo ID {photo_id} not found in database")
                continue

            result = self.process_photo(photo_id, photo["file_path"])

            if result:
                results["photos_processed"] += 1
                if result["primary_jersey"]:
                    results["jerseys_found"] += 1
            else:
                results["errors"] += 1

        logger.info(f"Batch processing complete: {results}")
        return results

    @staticmethod
    def _extract_jerseys_from_text(text: str) -> List[str]:
        """
        Extract jersey numbers (1-3 digit numbers) from text.

        Args:
            text: Raw text from OCR

        Returns:
            List of unique jersey numbers found
        """
        # Match 1-3 digit numbers, with word boundaries
        pattern = r"\b(\d{1,3})\b"
        matches = re.findall(pattern, text)

        # Filter to valid jersey numbers (exclude common OCR artifacts like year dates)
        # Keep 1-99 as valid jerseys, exclude 3-digit numbers > 999 or < 100
        valid_jerseys = []
        for num in matches:
            num_int = int(num)
            # Valid jerseys: 1-99
            if 1 <= num_int <= 99:
                if num not in valid_jerseys:  # Avoid duplicates
                    valid_jerseys.append(num)

        return valid_jerseys
