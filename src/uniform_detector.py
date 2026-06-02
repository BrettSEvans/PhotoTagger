import cv2
import numpy as np
import logging
from typing import Dict, Tuple, Optional
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UniformDetector:
    """Detect team uniform colors using histogram matching."""

    def __init__(self):
        """Initialize detector with reference color histograms."""
        logger.info("Initializing UniformDetector with histogram matching")
        self.reference_histograms = self._create_reference_histograms()

    def _create_reference_histograms(self) -> Dict[str, np.ndarray]:
        """
        Create reference histograms for common uniform colors.
        HSV: H=0-180, S=0-255, V=0-255
        """
        histograms = {}

        # Red: H = 0-10 or 170-180 (wraps around)
        # Create a synthetic histogram for red
        red_hist = np.zeros((256, 256), dtype=np.float32)
        red_hist[0:10, 100:255] = 1.0  # Red hue, high saturation
        histograms['red'] = cv2.normalize(red_hist, red_hist).astype(np.float32)

        # White: S = 0-30 (low saturation), V = 200-255 (high value)
        white_hist = np.zeros((256, 256), dtype=np.float32)
        white_hist[0:180, 0:30] = 1.0  # All hues, low saturation (appears white/gray)
        histograms['white'] = cv2.normalize(white_hist, white_hist).astype(np.float32)

        # Black: V = 0-50 (low value/brightness)
        black_hist = np.zeros((256, 256), dtype=np.float32)
        black_hist[0:180, 0:255] = 1.0  # Any hue/saturation, but low V
        # Apply brightness mask
        black_hist = np.where(black_hist > 0, 0.5, 0)  # Will be masked by V channel
        histograms['black'] = cv2.normalize(black_hist, black_hist).astype(np.float32)

        # Blue: H = 100-130
        blue_hist = np.zeros((256, 256), dtype=np.float32)
        blue_hist[100:130, 100:255] = 1.0  # Blue hue, high saturation
        histograms['blue'] = cv2.normalize(blue_hist, blue_hist).astype(np.float32)

        # Yellow: H = 20-30
        yellow_hist = np.zeros((256, 256), dtype=np.float32)
        yellow_hist[20:30, 100:255] = 1.0  # Yellow hue, high saturation
        histograms['yellow'] = cv2.normalize(yellow_hist, yellow_hist).astype(np.float32)

        return histograms

    def sample_face_jersey(self, img_bgr: np.ndarray, bbox) -> Tuple[Optional[str], float, Dict]:
        """
        Classify the jersey color from the torso patch directly below a face bbox.

        Unlike detect_uniform_color (which samples the whole image and assumes a
        single subject), this isolates ONE person's torso so multi-player crowd
        shots can be discriminated face-by-face.

        Args:
            img_bgr: Full image in BGR (as read by cv2.imread)
            bbox: [x0, y0, x1, y1] face bounding box in pixels

        Returns:
            (color_name | None, confidence_0_to_1, raw_analysis_dict)
        """
        try:
            h, w = img_bgr.shape[:2]
            x0, y0, x1, y1 = [int(v) for v in bbox]
            fw = max(1, x1 - x0)
            fh = max(1, y1 - y0)
            cx = (x0 + x1) // 2

            # Torso patch: start just below the chin (small neck gap), extend ~1.9
            # face-heights down, and ~0.9 face-widths to each side of the face center.
            ty0 = min(h, y1 + int(0.15 * fh))
            ty1 = min(h, y1 + int(1.9 * fh))
            tx0 = max(0, cx - int(0.9 * fw))
            tx1 = min(w, cx + int(0.9 * fw))

            if ty1 <= ty0 or tx1 <= tx0:
                return None, 0.0, {}

            patch = img_bgr[ty0:ty1, tx0:tx1]
            if patch.size == 0:
                return None, 0.0, {}

            hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
            analysis = self._analyze_region(hsv)
            color, conf = self._match_color(analysis)
            return color, float(conf), analysis
        except Exception as e:
            logger.error(f"Error sampling jersey below face: {e}")
            return None, 0.0, {}

    def detect_uniform_color(self, image_path: str) -> Optional[Dict]:
        """
        Detect team uniform colors using histogram matching.

        Returns:
            {
                'shirt_color': 'red' | 'white' | 'blue' | etc,
                'shirt_confidence': 0.0-1.0,
                'shirt_h_ratio': percentage of red/blue hues,
                'shirt_s_ratio': saturation level,
                'shirt_v_ratio': brightness level,
                'shorts_color': 'black' | 'white' | etc,
                'shorts_confidence': 0.0-1.0,
                'raw_histogram': {...}
            }
        """
        try:
            path = Path(image_path)
            if not path.exists():
                logger.warning(f"Image not found: {image_path}")
                return None

            img = cv2.imread(str(image_path))
            if img is None:
                logger.warning(f"Failed to read image: {image_path}")
                return None

            # Convert to HSV for better color detection
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

            # Analyze shirt (upper region, excluding head)
            height = hsv.shape[0]
            width = hsv.shape[1]

            # Upper region: 20% from top to 55% down (upper body)
            shirt_start = int(height * 0.20)
            shirt_end = int(height * 0.55)
            shirt_region = hsv[shirt_start:shirt_end, :]

            # Lower region: 55% down to bottom (shorts/legs)
            shorts_start = int(height * 0.55)
            shorts_region = hsv[shorts_start:, :]

            # Analyze colors
            shirt_analysis = self._analyze_region(shirt_region)
            shorts_analysis = self._analyze_region(shorts_region)

            # Match to known colors
            shirt_color, shirt_conf = self._match_color(shirt_analysis)
            shorts_color, shorts_conf = self._match_color(shorts_analysis)

            return {
                'shirt_color': shirt_color,
                'shirt_confidence': shirt_conf,
                'shirt_h_ratio': shirt_analysis['h_ratio'],
                'shirt_s_ratio': shirt_analysis['s_ratio'],
                'shirt_v_ratio': shirt_analysis['v_ratio'],
                'shorts_color': shorts_color,
                'shorts_confidence': shorts_conf,
                'shorts_h_ratio': shorts_analysis['h_ratio'],
                'shorts_s_ratio': shorts_analysis['s_ratio'],
                'shorts_v_ratio': shorts_analysis['v_ratio'],
            }

        except Exception as e:
            logger.error(f"Error detecting uniform in {image_path}: {e}")
            return None

    def _analyze_region(self, hsv_region: np.ndarray) -> Dict:
        """
        Analyze HSV values in a region.

        Returns histogram and color ratios.
        """
        if hsv_region.size == 0:
            return {'h_ratio': 0, 's_ratio': 0, 'v_ratio': 0}

        h = hsv_region[:, :, 0]
        s = hsv_region[:, :, 1]
        v = hsv_region[:, :, 2]

        # Skip near-black/white pixels (likely shadows or highlights)
        # Only analyze pixels with reasonable saturation and brightness
        mask = (s > 20) & (v > 30) & (v < 250)

        if np.sum(mask) == 0:
            # Region is mostly shadows/highlights, use all pixels
            mask = np.ones_like(h, dtype=bool)

        h_masked = h[mask]
        s_masked = s[mask]
        v_masked = v[mask]

        # Calculate ratios for key colors
        red_pixels = np.sum(((h_masked < 10) | (h_masked > 170)) & (s_masked > 100))
        white_pixels = np.sum((s_masked < 30) & (v_masked > 200))
        black_pixels = np.sum(v_masked < 50)
        blue_pixels = np.sum((h_masked >= 100) & (h_masked <= 130) & (s_masked > 100))

        total = len(h_masked)

        return {
            'h_ratio': np.mean(h_masked) / 180.0 if total > 0 else 0,
            's_ratio': np.mean(s_masked) / 255.0 if total > 0 else 0,
            'v_ratio': np.mean(v_masked) / 255.0 if total > 0 else 0,
            'red_ratio': red_pixels / total if total > 0 else 0,
            'white_ratio': white_pixels / total if total > 0 else 0,
            'black_ratio': black_pixels / total if total > 0 else 0,
            'blue_ratio': blue_pixels / total if total > 0 else 0,
        }

    def _match_color(self, analysis: Dict) -> Tuple[str, float]:
        """
        Match analyzed region to a color based on ratios.

        Returns:
            (color_name, confidence_0_to_1)
        """
        scores = {}

        # Red: high saturation, hue around 0
        red_score = (analysis['red_ratio'] * 0.7 +
                     (1 - abs(analysis['h_ratio'] - 0)) * 0.3 +
                     analysis['s_ratio'] * 0.3)
        scores['red'] = min(red_score, 1.0)

        # White: low saturation, high brightness
        white_score = ((1 - analysis['s_ratio']) * 0.6 +
                       analysis['v_ratio'] * 0.4 +
                       analysis['white_ratio'] * 0.5)
        scores['white'] = min(white_score, 1.0)

        # Black: low brightness
        black_score = ((1 - analysis['v_ratio']) * 0.8 +
                       analysis['black_ratio'] * 0.5)
        scores['black'] = min(black_score, 1.0)

        # Blue: high saturation, hue around 110
        blue_score = (analysis['blue_ratio'] * 0.7 +
                      (1 - abs(analysis['h_ratio'] - 110/180)) * 0.3 +
                      analysis['s_ratio'] * 0.3)
        scores['blue'] = min(blue_score, 1.0)

        # Yellow: saturation, hue around 25
        yellow_score = ((1 - analysis['h_ratio']) * 0.3 +
                        analysis['s_ratio'] * 0.4 +
                        analysis['v_ratio'] * 0.3)
        scores['yellow'] = min(yellow_score, 1.0)

        # Find best match
        best_color = max(scores, key=scores.get)
        confidence = scores[best_color]

        return best_color, confidence
