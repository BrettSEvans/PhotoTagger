import logging
import re
import time
from typing import List, Optional, Dict
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
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

    @staticmethod
    def _preprocess_for_ocr(photo_path: str):
        """
        Load and preprocess image for jersey number OCR.

        Steps:
          1. Load with OpenCV
          2. Upscale 4x (small thumbnails need this to read jersey digits)
          3. Convert to grayscale
          4. CLAHE contrast enhancement
          5. Unsharp mask sharpening

        Returns numpy array ready for EasyOCR, or None on failure.
        """
        import cv2
        import numpy as np

        img = cv2.imread(photo_path)
        if img is None:
            return None

        # 4x upscale — jersey digits on 576×384px are ~8-12px tall; need ≥32px for OCR
        scale = 4
        big = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)

        # Grayscale
        gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)

        # CLAHE — boost local contrast without blowing out highlights
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
        enhanced = clahe.apply(gray)

        # Unsharp mask sharpening
        blurred = cv2.GaussianBlur(enhanced, (0, 0), 2)
        sharpened = cv2.addWeighted(enhanced, 1.5, blurred, -0.5, 0)

        return sharpened

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

            # Preprocess: 4x upscale + CLAHE + sharpen for small thumbnails
            logger.info(f"Processing photo: {photo_path}")
            preprocessed = self._preprocess_for_ocr(photo_path)
            if preprocessed is None:
                logger.error(f"Failed to preprocess image: {photo_path}")
                return None

            # Run OCR — digits only, no paragraph merging
            results = self.reader.readtext(preprocessed, allowlist='0123456789', paragraph=False)

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
        # Load the photo table once and index by id (avoids an O(N²) reload per photo).
        photos_by_id = {p["id"]: p for p in self.db.get_all_photos()}
        if photo_ids is None:
            photo_ids = list(photos_by_id.keys())

        results = {
            "photos_processed": 0,
            "jerseys_found": 0,
            "errors": 0,
        }

        for photo_id in photo_ids:
            photo = photos_by_id.get(photo_id)

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

    def process_batch_parallel(self, photo_ids: List[int] = None, max_workers: int = None) -> Dict:
        """
        Process multiple photos in parallel using thread pool.

        Args:
            photo_ids: Optional list of photo IDs. If None, process all.
            max_workers: Number of parallel workers. If None, use optimal from config.

        Returns:
            Dict with processing statistics
        """
        from src.config import get_optimal_worker_count

        if max_workers is None:
            max_workers = get_optimal_worker_count()

        # Load the photo table once and index by id (avoids an O(N²) reload per photo).
        photos_by_id = {p["id"]: p for p in self.db.get_all_photos()}
        if photo_ids is None:
            photo_ids = list(photos_by_id.keys())

        results = {
            "photos_processed": 0,
            "jerseys_found": 0,
            "faces_detected": 0,
            "errors": 0,
            "start_time": time.time(),
        }

        if not photo_ids:
            results["elapsed_time"] = time.time() - results["start_time"]
            return results

        logger.info(f"Starting parallel OCR with {max_workers} workers on {len(photo_ids)} photos")

        # Use ThreadPoolExecutor for I/O-bound OCR
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            futures = {}
            for photo_id in photo_ids:
                photo = photos_by_id.get(photo_id)

                if photo:
                    future = executor.submit(self._process_photo_with_faces, photo_id, photo["file_path"])
                    futures[future] = photo_id

            # Collect results as they complete
            for future in as_completed(futures):
                photo_id = futures[future]
                try:
                    result = future.result()
                    if result:
                        results["photos_processed"] += 1
                        if result.get("primary_jersey"):
                            results["jerseys_found"] += 1
                        results["faces_detected"] += len(result.get("faces", []))
                except Exception as e:
                    logger.error(f"Error processing photo {photo_id}: {e}")
                    results["errors"] += 1

        results["elapsed_time"] = time.time() - results["start_time"]
        logger.info(f"Parallel processing complete: {results}")
        return results

    def _process_photo_with_faces(self, photo_id: int, photo_path: str) -> Optional[Dict]:
        """
        Internal method: process photo with OCR and face detection.

        Returns:
            Dict with jersey, faces, and metadata
        """
        try:
            from src.face_detector import FaceDetector
            from pathlib import Path

            path = Path(photo_path)
            if not path.exists():
                logger.error(f"Photo not found: {photo_path}")
                return None

            # Run OCR (jersey detection) — 4x upscale + CLAHE + sharpen
            logger.info(f"OCR: {path.name}")
            preprocessed = self._preprocess_for_ocr(photo_path)
            if preprocessed is not None:
                results = self.reader.readtext(preprocessed, allowlist='0123456789', paragraph=False)
            else:
                results = self.reader.readtext(photo_path)
            raw_text = " ".join([text for (_, text, _) in results])
            jerseys = self._extract_jerseys_from_text(raw_text)
            primary_jersey = jerseys[0] if jerseys else None
            ocr_confidence = sum([conf for (_, _, conf) in results]) / len(results) if results else 0.0

            # Run face detection
            logger.info(f"Faces: {path.name}")
            detector = FaceDetector()
            faces = detector.detect_faces(photo_path)

            # Store OCR result
            self.db.add_ocr_result(
                photo_id=photo_id,
                jersey_number=primary_jersey,
                confidence=ocr_confidence,
                raw_text=raw_text
            )

            # Store faces
            for face in faces:
                self.db.add_face(
                    photo_id=photo_id,
                    embedding=face['embedding'],
                    bbox=face['bbox'],
                    confidence=face['confidence']
                )

            return {
                "photo_id": photo_id,
                "jerseys_found": jerseys,
                "primary_jersey": primary_jersey,
                "faces": faces,
                "ocr_confidence": ocr_confidence,
            }

        except Exception as e:
            logger.error(f"Error processing photo {photo_path}: {e}")
            return None

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
