"""Jersey number recognition and roster matching."""

import logging
import os
import re
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import cv2
import numpy as np
import easyocr

from src import detection_utils
from src import config
from src.uniform_detector import UniformDetector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class JerseyRecognizer:
    """Extract jersey numbers from photos and match to roster using color and team context."""

    def __init__(self, db, languages: List[str] = None):
        """
        Initialize jersey recognizer.

        Args:
            db: Database connection (from current_app.db in Flask)
            languages: Languages for OCR (default: English)
        """
        self.db = db
        self.languages = languages or ["en"]
        logger.info(f"Initializing JerseyRecognizer with languages: {self.languages}")
        self.reader = easyocr.Reader(self.languages, gpu=False)
        self.uniform_detector = UniformDetector()
        # Per-game color-scheme learning (stubbed for now; would accumulate per team)
        self.learned_number_colors = {}

    @staticmethod
    def _compute_iou(box1: List[int], box2: List[int]) -> float:
        """
        Compute Intersection over Union (IoU) between two bboxes.

        Args:
            box1, box2: [x0, y0, x1, y1] bounding boxes

        Returns:
            IoU value (0-1)
        """
        x0_1, y0_1, x1_1, y1_1 = box1
        x0_2, y0_2, x1_2, y1_2 = box2

        # Intersection
        xi0 = max(x0_1, x0_2)
        yi0 = max(y0_1, y0_2)
        xi1 = min(x1_1, x1_2)
        yi1 = min(y1_1, y1_2)

        if xi1 <= xi0 or yi1 <= yi0:
            return 0.0

        inter = (xi1 - xi0) * (yi1 - yi0)
        area1 = (x1_1 - x0_1) * (y1_1 - y0_1)
        area2 = (x1_2 - x0_2) * (y1_2 - y0_2)
        union = area1 + area2 - inter

        return inter / union if union > 0 else 0.0

    @staticmethod
    def _extract_torso_crop(img_bgr: np.ndarray, face_bbox: List[int]) -> Optional[np.ndarray]:
        """
        Extract and preprocess torso region below a face for OCR.

        Uses the standard UniformDetector torso geometry:
        ty0 = y1 + 0.15*fh, ty1 = y1 + 1.9*fh, tx0/tx1 = cx ± 0.9*fw

        Args:
            img_bgr: Full image (BGR)
            face_bbox: [x0, y0, x1, y1] face bounding box

        Returns:
            Upscaled, preprocessed torso crop, or None if extraction fails
        """
        try:
            h, w = img_bgr.shape[:2]
            x0, y0, x1, y1 = [int(v) for v in face_bbox]
            fw = max(1, x1 - x0)
            fh = max(1, y1 - y0)
            cx = (x0 + x1) // 2

            # Torso patch geometry (matches UniformDetector.sample_face_jersey)
            ty0 = min(h - 1, y1 + int(0.15 * fh))
            ty1 = min(h, y1 + int(1.9 * fh))
            tx0 = max(0, cx - int(0.9 * fw))
            tx1 = min(w, cx + int(0.9 * fw))

            if ty1 <= ty0 or tx1 <= tx0:
                return None

            patch = img_bgr[ty0:ty1, tx0:tx1]
            if patch.size == 0:
                return None

            # Upscale the torso crop 4x for better OCR (not the whole frame)
            upscaled = cv2.resize(patch, None, fx=4, fy=4, interpolation=cv2.INTER_LANCZOS4)

            # Preprocess: grayscale + CLAHE + sharpening
            gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
            enhanced = clahe.apply(gray)
            blurred = cv2.GaussianBlur(enhanced, (0, 0), 2)
            sharpened = cv2.addWeighted(enhanced, 1.5, blurred, -0.5, 0)

            return sharpened
        except Exception as e:
            logger.error(f"Error extracting torso crop: {e}")
            return None

    @staticmethod
    def _validate_detection(bbox_ocr: Tuple, text: str, confidence: float,
                           scale_factor: float = 4, img_height: int = 384) -> Tuple[bool, Optional[int], Optional[int], Optional[int], Optional[int]]:
        """
        Validate an OCR detection against geometry and confidence filters.

        Returns:
            (is_valid, x0, y0, x1, y1) or (False, None, None, None, None)
        """
        # Confidence gate
        if confidence < config.OCR_MIN_CONFIDENCE:
            return False, None, None, None, None

        # Extract bbox from corner points
        try:
            xs = [pt[0] for pt in bbox_ocr]
            ys = [pt[1] for pt in bbox_ocr]
            x0_scaled = min(xs) / scale_factor
            y0_scaled = min(ys) / scale_factor
            x1_scaled = max(xs) / scale_factor
            y1_scaled = max(ys) / scale_factor

            x0 = max(0, int(x0_scaled))
            y0 = max(0, int(y0_scaled))
            x1 = max(x0 + 1, int(x1_scaled))
            y1 = max(y0 + 1, int(y1_scaled))
        except:
            return False, None, None, None, None

        # Aspect ratio check (very wide/short = text, not digits)
        width = x1 - x0
        height = y1 - y0
        aspect_ratio = width / height if height > 0 else 0
        if aspect_ratio > config.JERSEY_BBOX_MAX_ASPECT_RATIO:
            return False, None, None, None, None

        # Clamp to image bounds
        x1 = min(x1, 576)  # Assuming 576 width for -sm photos
        y1 = min(y1, img_height)

        return True, x0, y0, x1, y1

    @staticmethod
    def _spatial_dedup(detections: List[Dict]) -> List[Dict]:
        """
        Suppress detections that heavily overlap with higher-confidence ones.

        Args:
            detections: List of detection dicts with 'bbox' and 'confidence'

        Returns:
            Deduplicated list
        """
        if not detections:
            return []

        # Sort by confidence descending (keep high-confidence ones)
        sorted_dets = sorted(detections, key=lambda d: d.get('confidence', 0), reverse=True)
        kept = []

        for det in sorted_dets:
            bbox = det['bbox']
            overlaps = False

            for kept_det in kept:
                iou = JerseyRecognizer._compute_iou(bbox, kept_det['bbox'])
                if iou >= config.JERSEY_BBOX_OVERLAP_DEDUP_IOU:
                    overlaps = True
                    break

            if not overlaps:
                kept.append(det)

        return kept

    @staticmethod
    def _preprocess_for_ocr(photo_path: str) -> Optional[np.ndarray]:
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

    def process_photos(
        self,
        photo_ids: List[int],
        game_context: List[Dict],
    ) -> Dict[int, List[Dict]]:
        """
        Process a batch of photos for jersey number detection and roster matching.

        For each photo:
        1. Run OCR to extract jersey numbers and bounding boxes
        2. For each detected jersey number + bbox:
           - Match against roster using team + color + year from game context
           - Store in ocr_results table with roster_entry_id if matched
        3. Return matches organized by photo_id

        Args:
            photo_ids: List of photo IDs to process
            game_context: Active game context (list of dicts with team_name, team_year, uniform_color)

        Returns:
            Dict mapping photo_id -> list of jersey matches
            Each match: {
                "jersey_number": str,
                "confidence": float,
                "bbox": [x0, y0, x1, y1],
                "team_name": str or None,
                "player_name": str or None,
                "roster_entry_id": int or None,
            }
        """
        if not game_context:
            logger.warning("No game context provided for jersey matching")
            return {}

        photos_by_id = {p["id"]: p for p in self.db.photos.get_all_photos()}
        matches_by_photo = {}
        matched_count = 0
        total_detected = 0

        for photo_id in photo_ids:
            photo = photos_by_id.get(photo_id)
            if not photo:
                logger.warning(f"Photo ID {photo_id} not found in database")
                continue

            photo_path = photo.get("file_path", "")
            if not photo_path or not os.path.exists(photo_path):
                logger.warning(f"Photo path not accessible: {photo_path}")
                continue

            try:
                detections = self._process_photo_for_jerseys(photo_id, photo_path, game_context)
                matches_by_photo[photo_id] = detections
                total_detected += len(detections)
                for det in detections:
                    if det.get("roster_entry_id"):
                        matched_count += 1
            except Exception as e:
                logger.error(f"Error processing photo {photo_id}: {e}")
                matches_by_photo[photo_id] = []

        logger.info(f"Jersey recognition complete: {len(matches_by_photo)} photos, "
                    f"{total_detected} detections, {matched_count} matched to roster")
        return matches_by_photo

    def _process_photo_for_jerseys(
        self,
        photo_id: int,
        photo_path: str,
        game_context: List[Dict],
    ) -> List[Dict]:
        """
        Process a single photo for jersey number detection using hybrid approach:
        1. Torso-under-face OCR for front-facing players
        2. Standalone number region OCR for back-facing players (jersey-color validated)
        3. Per-detection filtering (confidence, digit-length, geometry, dedup)

        Args:
            photo_id: Database photo ID
            photo_path: Path to photo file
            game_context: Active game context

        Returns:
            List of jersey detections with roster matching
        """
        path = Path(photo_path)
        logger.info(f"Processing jersey for photo: {path.name}")

        # Load original image
        img_original = cv2.imread(photo_path)
        if img_original is None:
            logger.error(f"Could not load image: {photo_path}")
            return []

        height_orig, width_orig = img_original.shape[:2]
        detections = []

        # ─── PHASE 1: Torso-under-face OCR (front-facing players) ───
        try:
            faces = self.db.faces.get_faces_by_photo(photo_id)
            for face in faces:
                face_bbox = face['bbox']
                torso_crop = self._extract_torso_crop(img_original, face_bbox)

                if torso_crop is None:
                    continue

                # Run OCR on the torso crop
                try:
                    ocr_results = self.reader.readtext(torso_crop, allowlist='0123456789', paragraph=False)
                except Exception as e:
                    logger.debug(f"OCR failed on torso crop for face {face['id']}: {e}")
                    continue

                for bbox_ocr, text, confidence in ocr_results:
                    # Validate detection (confidence, digit-length, geometry)
                    is_valid, x0, y0, x1, y1 = self._validate_detection(
                        bbox_ocr, text, confidence,
                        scale_factor=4,
                        img_height=height_orig
                    )

                    if not is_valid:
                        continue

                    # Scale bbox back to original image space (torso_crop was 4x upscaled)
                    # and offset by the torso crop position in the full image
                    face_x0, face_y0, face_x1, face_y1 = face_bbox
                    fw = face_x1 - face_x0
                    fh = face_y1 - face_y0
                    cx = (face_x0 + face_x1) // 2
                    ty0 = min(height_orig - 1, face_y1 + int(0.15 * fh))
                    tx0 = max(0, cx - int(0.9 * fw))

                    bbox_orig = [
                        max(0, tx0 + x0),
                        max(0, ty0 + y0),
                        min(width_orig, tx0 + x1),
                        min(height_orig, ty0 + y1),
                    ]

                    # Normalize and validate digit-length
                    jersey_number = detection_utils.normalize_jersey_number(text)
                    if not jersey_number:
                        continue
                    if not (config.JERSEY_DIGIT_MIN_LENGTH <= len(jersey_number) <= config.JERSEY_DIGIT_MAX_LENGTH):
                        continue

                    # Build detection dict (will match roster later)
                    detection = {
                        "jersey_number": jersey_number,
                        "confidence": float(confidence),
                        "bbox": bbox_orig,
                        "text": text,
                        "face_id": face['id'],
                    }
                    detections.append(detection)

        except Exception as e:
            logger.warning(f"Torso-under-face OCR failed for photo {photo_id}: {e}")

        # ─── PHASE 2: Standalone number regions (back-facing players) ───
        # Scan the full frame for standalone digit regions not under a detected face.
        # Accept only if background is a team jersey color.
        try:
            preprocessed = self._preprocess_for_ocr(photo_path)
            if preprocessed is not None:
                ocr_results = self.reader.readtext(preprocessed, allowlist='0123456789', paragraph=False)

                for bbox_ocr, text, confidence in ocr_results:
                    is_valid, x0, y0, x1, y1 = self._validate_detection(
                        bbox_ocr, text, confidence,
                        scale_factor=4,
                        img_height=height_orig
                    )

                    if not is_valid:
                        continue

                    bbox = [x0, y0, x1, y1]

                    # Check if this bbox is already covered by a torso-under-face detection
                    already_detected = False
                    for det in detections:
                        if self._compute_iou(bbox, det['bbox']) > 0.3:
                            already_detected = True
                            break

                    if already_detected:
                        continue

                    # Validate jersey color background
                    # Sample color around the detected region
                    margin_x = max(5, (x1 - x0) // 2)
                    margin_y = max(5, (y1 - y0) // 2)
                    sample_x0 = max(0, x0 - margin_x)
                    sample_y0 = max(0, y0 - margin_y)
                    sample_x1 = min(width_orig, x1 + margin_x)
                    sample_y1 = min(height_orig, y1 + margin_y)

                    sample_region = img_original[sample_y0:sample_y1, sample_x0:sample_x1]
                    if sample_region.size == 0:
                        continue

                    color, color_conf, _ = self.uniform_detector.sample_face_jersey(img_original, [x0, y0, x1, y1])

                    # Only accept if color matches a game context uniform color
                    color_is_valid = False
                    if color and color_conf >= config.MIN_JERSEY_COLOR_CONF:
                        for team in game_context:
                            team_color = team.get("uniform_color", "").lower()
                            if team_color and color.lower() == team_color:
                                color_is_valid = True
                                break

                    if not color_is_valid:
                        continue

                    # Normalize and validate digit-length
                    jersey_number = detection_utils.normalize_jersey_number(text)
                    if not jersey_number:
                        continue
                    if not (config.JERSEY_DIGIT_MIN_LENGTH <= len(jersey_number) <= config.JERSEY_DIGIT_MAX_LENGTH):
                        continue

                    # Build detection dict
                    detection = {
                        "jersey_number": jersey_number,
                        "confidence": float(confidence),
                        "bbox": bbox,
                        "text": text,
                        "face_id": None,
                    }
                    detections.append(detection)

        except Exception as e:
            logger.warning(f"Standalone region OCR failed for photo {photo_id}: {e}")

        # ─── PHASE 3: Spatial dedup and roster matching ───
        detections = self._spatial_dedup(detections)

        final_detections = []
        for detection in detections:
            jersey_number = detection['jersey_number']

            # Match to roster
            roster_entry_id = None
            player_name = None
            team_name = None

            for team in game_context:
                entry = detection_utils.match_to_roster(
                    self.db,
                    jersey_number=jersey_number,
                    value_type="jersey_number",
                    team_name=team.get("team_name"),
                    jersey_color=team.get("uniform_color"),
                    year=team.get("team_year"),
                )
                if entry:
                    roster_entry_id = entry.get("id")
                    player_name = entry.get("player_name")
                    team_name = entry.get("team_name")
                    break

            # Store OCR result in database
            try:
                self.db.photos.add_ocr_result(
                    photo_id=photo_id,
                    jersey_number=jersey_number,
                    confidence=float(detection['confidence']),
                    raw_text=detection['text'],
                    uniform_color=game_context[0].get("uniform_color") if game_context else None,
                    bbox=detection['bbox'],
                    roster_entry_id=roster_entry_id,
                )
            except Exception as e:
                logger.warning(f"Could not store OCR result for photo {photo_id}: {e}")

            final_detections.append({
                "jersey_number": jersey_number,
                "confidence": float(detection['confidence']),
                "bbox": detection['bbox'],
                "team_name": team_name,
                "player_name": player_name,
                "roster_entry_id": roster_entry_id,
            })

        logger.info(f"Found {len(final_detections)} jersey detections in {path.name} (after filtering and dedup)")
        return final_detections

    def match_jersey_to_roster(
        self,
        jersey_number: str,
        team_name: str,
        jersey_color: str,
        year: int,
    ) -> Optional[Dict]:
        """
        Match a jersey number to a roster entry using all matching criteria.

        Args:
            jersey_number: Detected jersey number (e.g. "31")
            team_name: Team name from game context
            jersey_color: Uniform color from game context
            year: Tournament year

        Returns:
            Roster entry dict if unique match found, None otherwise
        """
        return detection_utils.match_to_roster(
            self.db,
            jersey_number=jersey_number,
            value_type="jersey_number",
            team_name=team_name,
            jersey_color=jersey_color,
            year=year,
        )
