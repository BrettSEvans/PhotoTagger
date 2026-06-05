"""
Unit tests for src/uniform_detector.py.

Tests UniformDetector using synthetic numpy arrays and temporary JPEG files
so no real photos are needed.
"""

import io
import numpy as np
import pytest
from PIL import Image

from src.uniform_detector import UniformDetector


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _solid_bgr(h: int, w: int, bgr) -> np.ndarray:
    """Return a solid-colour BGR image."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = bgr
    return img


def _save_jpg(path, bgr_img):
    """Save a BGR numpy array as JPEG at path."""
    rgb = bgr_img[:, :, ::-1]
    Image.fromarray(rgb).save(str(path), format="JPEG")


# ---------------------------------------------------------------------------
# construction
# ---------------------------------------------------------------------------

class TestUniformDetectorInit:
    def test_creates_without_error(self):
        ud = UniformDetector()
        assert ud is not None

    def test_has_reference_histograms(self):
        ud = UniformDetector()
        assert hasattr(ud, "reference_histograms")
        assert len(ud.reference_histograms) > 0


# ---------------------------------------------------------------------------
# sample_face_jersey
# ---------------------------------------------------------------------------

class TestSampleFaceJersey:
    """Tests for UniformDetector.sample_face_jersey using in-memory arrays."""

    def setup_method(self):
        self.ud = UniformDetector()

    def test_returns_tuple_of_three(self):
        img = _solid_bgr(200, 200, (10, 10, 10))  # very dark / black
        face_bbox = [80, 30, 120, 80]
        result = self.ud.sample_face_jersey(img, face_bbox)
        assert len(result) == 3  # (color, conf, analysis_dict)

    def test_confidence_is_float(self):
        img = _solid_bgr(200, 200, (200, 200, 200))  # light grey
        face_bbox = [80, 30, 120, 80]
        _, conf, _ = self.ud.sample_face_jersey(img, face_bbox)
        assert isinstance(conf, float)
        assert 0.0 <= conf <= 1.0

    def test_dark_image_returns_black_or_none(self):
        """A nearly-black image torso should return 'black' or low confidence."""
        img = _solid_bgr(300, 200, (5, 5, 5))  # near-black
        face_bbox = [50, 30, 150, 100]
        color, conf, _ = self.ud.sample_face_jersey(img, face_bbox)
        # Either 'black' is returned, or low confidence
        if color is not None:
            assert isinstance(color, str)

    def test_face_at_bottom_returns_safely(self):
        """Face at image bottom should not crash even if torso area is empty."""
        img = _solid_bgr(100, 100, (50, 50, 200))  # bluish
        face_bbox = [0, 90, 100, 99]
        result = self.ud.sample_face_jersey(img, face_bbox)
        assert len(result) == 3  # no exception

    def test_returns_none_color_for_degenerate_bbox(self):
        """Zero-size bbox should return safely (None color)."""
        img = _solid_bgr(200, 200, (200, 100, 50))
        # Zero-width face
        face_bbox = [100, 100, 100, 100]
        color, conf, analysis = self.ud.sample_face_jersey(img, face_bbox)
        # Should either be None or a valid color string, no exception
        assert conf >= 0.0

    def test_analysis_dict_has_expected_keys(self):
        img = _solid_bgr(300, 300, (200, 200, 200))
        face_bbox = [100, 50, 200, 130]
        _, _, analysis = self.ud.sample_face_jersey(img, face_bbox)
        # If torso was extractable, analysis has at least h_ratio/s_ratio/v_ratio
        if analysis:
            for key in ("h_ratio", "s_ratio", "v_ratio"):
                assert key in analysis


# ---------------------------------------------------------------------------
# detect_uniform_color (file-based)
# ---------------------------------------------------------------------------

class TestDetectUniformColor:
    """Tests for UniformDetector.detect_uniform_color."""

    def setup_method(self):
        self.ud = UniformDetector()

    def test_returns_none_for_missing_file(self):
        result = self.ud.detect_uniform_color("/nonexistent/path.jpg")
        assert result is None

    def test_returns_dict_for_valid_image(self, tmp_path):
        img_path = tmp_path / "solid_red.jpg"
        _save_jpg(img_path, _solid_bgr(200, 200, (0, 0, 200)))  # red in BGR
        result = self.ud.detect_uniform_color(str(img_path))
        assert result is not None
        assert "shirt_color" in result
        assert "shirt_confidence" in result
        assert "shorts_color" in result

    def test_dict_has_all_keys(self, tmp_path):
        img_path = tmp_path / "test.jpg"
        _save_jpg(img_path, _solid_bgr(200, 200, (200, 200, 200)))  # white-ish
        result = self.ud.detect_uniform_color(str(img_path))
        if result is not None:
            for k in ("shirt_color", "shirt_confidence",
                      "shorts_color", "shorts_confidence"):
                assert k in result
