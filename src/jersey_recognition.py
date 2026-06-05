"""Jersey number recognition and roster matching."""

import logging
import os
import re
import tempfile
import time
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import cv2
import numpy as np
import pytesseract
from PIL import Image

from src import detection_utils
from src import config
from src.uniform_detector import UniformDetector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level OCR readiness — set up once, cached forever
# ---------------------------------------------------------------------------
_ocr_ready: bool = False
_ocr_ok: Optional[bool] = None


def ensure_ocr_ready(project_root: Optional[str] = None) -> bool:
    """Set up a Tesseract-readable temp dir and run a self-test once.

    pytesseract round-trips images through ``$TMPDIR``.  On some systems
    (e.g. macOS sandbox envs) Leptonica cannot open files in the default
    ``/tmp/…`` or ``/var/folders/…`` paths — it reads the bytes as a filename
    and emits "image file not found", causing a non-zero exit and a
    ``UnicodeDecodeError`` in pytesseract.  Pointing the temp dir to a
    project-local path that Leptonica *can* read fixes this.

    This function is idempotent: the first call does the work, subsequent
    calls return the cached result immediately.

    Args:
        project_root: Absolute path to use as base for ``.ocr_tmp``.
                      Defaults to two levels above this file (the repo root).

    Returns:
        True if Tesseract can OCR a synthetic digit image, False otherwise.
    """
    global _ocr_ready, _ocr_ok
    if _ocr_ready:
        return bool(_ocr_ok)

    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent

    ocr_tmp = Path(project_root) / ".ocr_tmp"
    try:
        ocr_tmp.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Could not create OCR temp dir {ocr_tmp}: {e}")
        _ocr_ready = True
        _ocr_ok = False
        return False

    # Point pytesseract (and Leptonica) at the readable dir.
    tempfile.tempdir = str(ocr_tmp)
    os.environ["TMPDIR"] = str(ocr_tmp)

    # Self-test: synthesise a "19" image and verify OCR returns at least one digit.
    _ocr_ok = _self_test_ocr()
    _ocr_ready = True

    if _ocr_ok:
        logger.info(f"OCR self-test PASSED (temp dir: {ocr_tmp})")
    else:
        logger.error(
            f"OCR self-test FAILED — Tesseract cannot process images via temp dir "
            f"{ocr_tmp}.  Jersey detection will produce 0 results.  "
            f"Check that Tesseract is installed and $TMPDIR is accessible."
        )
    return bool(_ocr_ok)


def _self_test_ocr() -> bool:
    """OCR a synthetic '19' image. Returns True if any digits are read back."""
    try:
        # Build a white-on-black digit image with OpenCV (no font file needed).
        img = np.ones((80, 120), dtype=np.uint8) * 255
        cv2.putText(img, "19", (8, 62), cv2.FONT_HERSHEY_SIMPLEX, 2.0, 0, 3)
        pil = Image.fromarray(img)
        result = pytesseract.image_to_string(
            pil,
            config="--psm 8 --oem 3 -c tessedit_char_whitelist=0123456789",
        ).strip()
        return len(result) > 0
    except Exception as e:
        logger.error(f"OCR self-test exception: {type(e).__name__}: {e}")
        return False


class JerseyRecognizer:
    """Extract jersey numbers from photos and match to roster using color and team context."""

    def __init__(self, db, languages: List[str] = None):
        """
        Initialize jersey recognizer with Tesseract OCR backend.

        Args:
            db: Database connection (from current_app.db in Flask)
            languages: Languages for OCR (ignored, kept for compatibility)
        """
        self.db = db
        self.languages = languages or ["en"]
        # Ensure temp dir is readable and backend is functional (idempotent).
        ensure_ocr_ready()
        logger.info(f"Initializing JerseyRecognizer with Tesseract OCR backend (ocr_ok={_ocr_ok})")
        self.uniform_detector = UniformDetector()
        # Per-game color-scheme learning (stubbed for now; would accumulate per team)
        self.learned_number_colors = {}

    @staticmethod
    def _tesseract_ocr_digits(image_bgr: np.ndarray, psm: int = 8) -> List[Tuple]:
        """
        Run Tesseract OCR on preprocessed image to extract digit numbers.

        Args:
            image_bgr: Preprocessed image (BGR numpy array OR grayscale, already upscaled
                       and enhanced).
            psm: Tesseract page-segmentation mode.
                 8 = single word (tight torso crops, Phase 1).
                 11 = sparse text (wide uncovered-region bands, Phase 2).

        Returns:
            List of (bbox, text, confidence) tuples.

        Raises:
            Any exception from pytesseract so callers can log it at the appropriate
            level and decide whether to skip the crop or abort the photo.  We no
            longer silently swallow backend failures.
        """
        # Handle both BGR (3-channel) and grayscale (1-channel) arrays.
        if image_bgr.ndim == 2:
            pil_image = Image.fromarray(image_bgr)
        else:
            image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(image_rgb)

        # Configure Tesseract for digit-only detection.
        # --oem 3: Use both legacy and LSTM engine.
        config_str = f"--psm {psm} --oem 3 -c tessedit_char_whitelist=0123456789"

        # Get detailed results including bounding boxes and confidence.
        # NOTE: pytesseract writes the image to $TMPDIR before calling tesseract.
        # If $TMPDIR is not readable by Leptonica this will raise; ensure_ocr_ready()
        # must have been called first.
        ocr_results = pytesseract.image_to_data(
            pil_image,
            config=config_str,
            output_type=pytesseract.Output.DICT,
        )

        detections = []
        if ocr_results["text"]:
            for i, text in enumerate(ocr_results["text"]):
                if not text.strip():  # Skip empty detections
                    continue

                confidence = int(ocr_results["conf"][i]) / 100.0
                if confidence < 0.3:  # Skip very low confidence
                    continue

                # Extract bbox from Tesseract output
                x0 = ocr_results["left"][i]
                y0 = ocr_results["top"][i]
                x1 = x0 + ocr_results["width"][i]
                y1 = y0 + ocr_results["height"][i]

                # Return in format compatible with previous EasyOCR code.
                bbox_ocr = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
                detections.append((bbox_ocr, text, confidence))

        return detections

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

        t_batch_start = time.time()
        logger.info(f"[TIMING] Jersey recognition batch start: {len(photo_ids)} photos")

        photos_by_id = {p["id"]: p for p in self.db.photos.get_all_photos()}
        matches_by_photo = {}
        matched_count = 0
        total_detected = 0

        for i, photo_id in enumerate(photo_ids):
            photo = photos_by_id.get(photo_id)
            if not photo:
                logger.warning(f"Photo ID {photo_id} not found in database")
                continue

            photo_path = photo.get("file_path", "")
            if not photo_path or not os.path.exists(photo_path):
                logger.warning(f"Photo path not accessible: {photo_path}")
                continue

            try:
                t_photo_start = time.time()
                detections = self._process_photo_for_jerseys(photo_id, photo_path, game_context)
                t_photo = time.time() - t_photo_start

                matches_by_photo[photo_id] = detections
                total_detected += len(detections)
                matched_in_photo = sum(1 for d in detections if d.get("roster_entry_id"))
                matched_count += matched_in_photo

                logger.info(f"[TIMING] Photo {photo_id} ({i+1}/{len(photo_ids)}): {t_photo:.2f}s "
                           f"({len(detections)} detections, {matched_in_photo} matched)")
            except Exception as e:
                logger.error(f"Error processing photo {photo_id}: {e}")
                matches_by_photo[photo_id] = []

        t_batch = time.time() - t_batch_start
        logger.info(f"[TIMING] Jersey recognition batch complete: {t_batch:.2f}s total, "
                   f"{len(matches_by_photo)} photos, {total_detected} detections, {matched_count} matched to roster")
        return matches_by_photo

    def _find_uncovered_torso_regions(
        self,
        img_bgr: np.ndarray,
        detected_face_bboxes: List[List[int]],
    ) -> List[List[int]]:
        """
        Find torso-height regions not covered by detected faces.

        Jersey numbers always appear in the torso region (between arms, head on top, waist on bottom).
        This method identifies vertical bands that don't have a detected face in the torso zone,
        then returns torso-height crops to OCR for back-facing players.

        Args:
            img_bgr: Full image (BGR)
            detected_face_bboxes: List of face bboxes [x0, y0, x1, y1]

        Returns:
            List of torso region crops [x0, y0, x1, y1] to OCR
        """
        h, w = img_bgr.shape[:2]
        uncovered = []

        if not detected_face_bboxes:
            # No faces detected, scan the entire torso region
            # Torso region: from ~head height to waist (y=30% to y=80% of image)
            y0 = int(h * 0.20)
            y1 = int(h * 0.85)

            # Divide into 2-3 vertical bands to scan
            band_width = w // 3
            for x in range(0, w, band_width):
                x0 = x
                x1 = min(x + band_width + 20, w)  # Small overlap for continuity
                uncovered.append([x0, y0, x1, y1])
            return uncovered

        # Mark torso zones covered by detected faces
        # For each face, the torso extends below it
        covered_zones = []
        for face_bbox in detected_face_bboxes:
            x0, y0, x1, y1 = [int(v) for v in face_bbox]
            fw = max(1, x1 - x0)
            fh = max(1, y1 - y0)

            # Torso zone: from neck (y1) to waist (y1 + 2.0*fh)
            # Horizontal: from shoulders (x0 - 0.5*fw) to (x1 + 0.5*fw)
            torso_x0 = max(0, x0 - int(0.5 * fw))
            torso_x1 = min(w, x1 + int(0.5 * fw))
            torso_y0 = y1  # Start at neck
            torso_y1 = min(h, y1 + int(2.0 * fh))  # End at waist

            covered_zones.append([torso_x0, torso_y0, torso_x1, torso_y1])

        # Find horizontal bands not covered
        # Strategy: scan vertical bands and skip those with face coverage
        band_width = max(60, w // 4)  # Scan bands of ~60px or image-width/4

        for x_start in range(0, w, band_width):
            x_end = min(x_start + band_width, w)
            band_center_x = (x_start + x_end) / 2

            # Check if this x-band has face coverage
            has_face_coverage = False
            for cx0, cy0, cx1, cy1 in covered_zones:
                if cx0 <= band_center_x <= cx1:
                    has_face_coverage = True
                    break

            if not has_face_coverage:
                # This band has no face; scan the torso region vertically
                torso_y0 = int(h * 0.20)  # Top of torso (below head)
                torso_y1 = int(h * 0.85)  # Bottom of torso (above legs)
                uncovered.append([x_start, torso_y0, x_end, torso_y1])

        return uncovered

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
        t_phase1 = time.time()
        try:
            faces = self.db.faces.get_faces_by_photo(photo_id)
            for face in faces:
                face_bbox = face['bbox']
                torso_crop = self._extract_torso_crop(img_original, face_bbox)

                if torso_crop is None:
                    continue

                # Run OCR on the torso crop using Tesseract (psm 8 = single word)
                try:
                    ocr_results = self._tesseract_ocr_digits(torso_crop, psm=8)
                except Exception as e:
                    logger.warning(f"OCR failed on torso crop for face {face['id']}: {type(e).__name__}: {e}")
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

        t_phase1_duration = time.time() - t_phase1
        logger.info(f"[TIMING] Photo {photo_id} Phase 1 (torso-under-face): {t_phase1_duration:.2f}s ({len(detections)} detections)")

        # ─── PHASE 2: Uncovered-region OCR (back-facing players) ───
        # Find torso regions not covered by detected faces and scan those for jersey numbers.
        # This avoids expensive full-frame preprocessing.
        t_phase2 = time.time()
        try:
            detected_face_bboxes = [f['bbox'] for f in self.db.faces.get_faces_by_photo(photo_id)]
            uncovered_regions = self._find_uncovered_torso_regions(img_original, detected_face_bboxes)

            for region_bbox in uncovered_regions:
                x0, y0, x1, y1 = region_bbox
                x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)

                # Clamp to image bounds
                x0 = max(0, x0)
                y0 = max(0, y0)
                x1 = min(width_orig, x1)
                y1 = min(height_orig, y1)

                if x1 <= x0 or y1 <= y0:
                    continue

                # Extract torso-region crop
                region_crop = img_original[y0:y1, x0:x1]
                if region_crop.size == 0:
                    continue

                # Upscale the region 4x (not the whole frame)
                upscaled = cv2.resize(region_crop, None, fx=4, fy=4, interpolation=cv2.INTER_LANCZOS4)

                # Preprocess: grayscale + CLAHE + sharpening
                gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
                clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
                enhanced = clahe.apply(gray)
                blurred = cv2.GaussianBlur(enhanced, (0, 0), 2)
                sharpened = cv2.addWeighted(enhanced, 1.5, blurred, -0.5, 0)

                # Run OCR on the preprocessed region crop using Tesseract.
                # psm 11 (sparse text) is better for wide bands with multiple sparse numbers.
                try:
                    ocr_results = self._tesseract_ocr_digits(sharpened, psm=11)
                except Exception as e:
                    logger.warning(f"OCR failed on region [{x0}:{x1}, {y0}:{y1}] for photo {photo_id}: {type(e).__name__}: {e}")
                    continue

                for bbox_ocr, text, confidence in ocr_results:
                    is_valid, rx0, ry0, rx1, ry1 = self._validate_detection(
                        bbox_ocr, text, confidence,
                        scale_factor=4,
                        img_height=(y1 - y0)  # Region height, not full image
                    )

                    if not is_valid:
                        continue

                    # Translate region-relative coords back to full-image space
                    bbox = [x0 + rx0, y0 + ry0, x0 + rx1, y0 + ry1]

                    # Check if this bbox is already covered by a torso-under-face detection
                    already_detected = False
                    for det in detections:
                        if self._compute_iou(bbox, det['bbox']) > 0.3:
                            already_detected = True
                            break

                    if already_detected:
                        continue

                    # Validate jersey color background
                    color, color_conf, _ = self.uniform_detector.sample_face_jersey(img_original, bbox)

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
            logger.warning(f"Uncovered-region OCR failed for photo {photo_id}: {e}")

        t_phase2_duration = time.time() - t_phase2
        logger.info(f"[TIMING] Photo {photo_id} Phase 2 (uncovered regions): {t_phase2_duration:.2f}s")

        # ─── PHASE 3: Spatial dedup and roster matching ───
        t_phase3 = time.time()
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

        t_phase3_duration = time.time() - t_phase3
        logger.info(f"[TIMING] Photo {photo_id} Phase 3 (dedup + matching): {t_phase3_duration:.2f}s")
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
