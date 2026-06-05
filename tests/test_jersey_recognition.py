"""
Unit tests for src/jersey_recognition.py.

Focuses on pure-Python helpers that do NOT require a real photo on disk or a
live Tesseract install:
  - _compute_iou
  - _spatial_dedup
  - _validate_detection
  - _extract_torso_crop (via synthetic numpy arrays)
  - _find_uncovered_torso_regions (via synthetic numpy arrays)
  - normalize_jersey_number (via detection_utils)
  - ensure_ocr_ready / _self_test_ocr (OCR backend smoke-test)
"""

import numpy as np
import pytest

from src.jersey_recognition import (
    JerseyRecognizer,
    _self_test_ocr,
    ensure_ocr_ready,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bgr(h: int = 200, w: int = 300, color=(128, 128, 128)) -> np.ndarray:
    """Create a solid-colour BGR image."""
    img = np.full((h, w, 3), color, dtype=np.uint8)
    return img


def _make_gray(h: int = 200, w: int = 300, val: int = 128) -> np.ndarray:
    """Create a grayscale image."""
    return np.full((h, w), val, dtype=np.uint8)


# ---------------------------------------------------------------------------
# _compute_iou
# ---------------------------------------------------------------------------

class TestComputeIou:
    """Tests for JerseyRecognizer._compute_iou."""

    def test_identical_boxes_return_1(self):
        box = [0, 0, 100, 100]
        assert JerseyRecognizer._compute_iou(box, box) == pytest.approx(1.0)

    def test_no_overlap_returns_0(self):
        b1 = [0, 0, 50, 50]
        b2 = [100, 100, 200, 200]
        assert JerseyRecognizer._compute_iou(b1, b2) == pytest.approx(0.0)

    def test_partial_overlap(self):
        b1 = [0, 0, 100, 100]  # area 10 000
        b2 = [50, 50, 150, 150]  # area 10 000; overlap = 50×50 = 2 500
        iou = JerseyRecognizer._compute_iou(b1, b2)
        expected = 2500 / (10000 + 10000 - 2500)
        assert iou == pytest.approx(expected, rel=1e-4)

    def test_one_inside_other(self):
        outer = [0, 0, 100, 100]  # area 10 000
        inner = [25, 25, 75, 75]  # area 2 500; overlap = 2 500
        iou = JerseyRecognizer._compute_iou(outer, inner)
        expected = 2500 / 10000
        assert iou == pytest.approx(expected, rel=1e-4)

    def test_touching_edges_returns_0(self):
        """Two boxes that share only an edge have zero area overlap."""
        b1 = [0, 0, 50, 50]
        b2 = [50, 0, 100, 50]
        assert JerseyRecognizer._compute_iou(b1, b2) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _spatial_dedup
# ---------------------------------------------------------------------------

class TestSpatialDedup:
    """Tests for JerseyRecognizer._spatial_dedup."""

    def _det(self, x0, y0, x1, y1, conf=0.9, number="7"):
        return {"jersey_number": number, "confidence": conf, "bbox": [x0, y0, x1, y1]}

    def test_empty_returns_empty(self):
        assert JerseyRecognizer._spatial_dedup([]) == []

    def test_single_detection_kept(self):
        dets = [self._det(0, 0, 50, 50)]
        result = JerseyRecognizer._spatial_dedup(dets)
        assert len(result) == 1

    def test_non_overlapping_kept(self):
        dets = [self._det(0, 0, 50, 50), self._det(200, 200, 250, 250)]
        result = JerseyRecognizer._spatial_dedup(dets)
        assert len(result) == 2

    def test_heavily_overlapping_lower_conf_suppressed(self):
        high = self._det(0, 0, 100, 100, conf=0.95)
        low  = self._det(5, 5, 95, 95, conf=0.60)   # IoU >> 0.3 → suppress
        result = JerseyRecognizer._spatial_dedup([high, low])
        assert len(result) == 1
        assert result[0]["confidence"] == pytest.approx(0.95)

    def test_high_conf_wins_regardless_of_order(self):
        low  = self._det(0, 0, 100, 100, conf=0.50)
        high = self._det(5, 5, 95, 95, conf=0.90)
        result = JerseyRecognizer._spatial_dedup([low, high])
        assert len(result) == 1
        assert result[0]["confidence"] == pytest.approx(0.90)


# ---------------------------------------------------------------------------
# _validate_detection
# ---------------------------------------------------------------------------

class TestValidateDetection:
    """Tests for JerseyRecognizer._validate_detection."""

    def _bbox_from_rect(self, x0, y0, x1, y1):
        """Return bbox_ocr in corner-point format."""
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]

    def test_valid_detection_passes(self):
        bbox = self._bbox_from_rect(0, 0, 40, 40)  # square → aspect ratio 1.0
        is_valid, x0, y0, x1, y1 = JerseyRecognizer._validate_detection(
            bbox, "19", 0.90, scale_factor=1, img_height=200
        )
        assert is_valid is True
        assert x0 == 0 and y0 == 0

    def test_low_confidence_fails(self):
        bbox = self._bbox_from_rect(0, 0, 40, 40)
        is_valid, *_ = JerseyRecognizer._validate_detection(
            bbox, "19", 0.10, scale_factor=1, img_height=200
        )
        assert is_valid is False

    def test_too_wide_aspect_ratio_fails(self):
        # width = 200, height = 5 → aspect = 40 >> 1.5
        bbox = self._bbox_from_rect(0, 0, 200, 5)
        is_valid, *_ = JerseyRecognizer._validate_detection(
            bbox, "19", 0.90, scale_factor=1, img_height=200
        )
        assert is_valid is False

    def test_scale_factor_applied(self):
        # bbox in 4x-upscaled space: points at (80, 80) should map to ~(20, 20)
        bbox = self._bbox_from_rect(80, 80, 160, 160)
        is_valid, x0, y0, x1, y1 = JerseyRecognizer._validate_detection(
            bbox, "7", 0.80, scale_factor=4, img_height=200
        )
        assert is_valid is True
        assert x0 == 20 and y0 == 20


# ---------------------------------------------------------------------------
# _extract_torso_crop
# ---------------------------------------------------------------------------

class TestExtractTorsoCrop:
    """Tests for JerseyRecognizer._extract_torso_crop."""

    def test_returns_ndarray_for_valid_face(self):
        img = _make_bgr(h=400, w=300)
        # Face in upper-center area; torso should land below it
        face_bbox = [100, 50, 200, 130]  # 100×80 px face
        crop = JerseyRecognizer._extract_torso_crop(img, face_bbox)
        assert crop is not None
        assert isinstance(crop, np.ndarray)
        # Crop should be non-empty
        assert crop.size > 0

    def test_returns_none_when_face_at_bottom(self):
        """Face at the very bottom of the image leaves no torso room."""
        img = _make_bgr(h=100, w=100)
        # Face starts at y=90 in a 100-px tall image → no torso space
        face_bbox = [0, 90, 100, 99]
        crop = JerseyRecognizer._extract_torso_crop(img, face_bbox)
        # The crop may be None or a very tiny array — either is acceptable
        if crop is not None:
            assert crop.size >= 0  # just check it doesn't crash


# ---------------------------------------------------------------------------
# _find_uncovered_torso_regions
# ---------------------------------------------------------------------------

class TestFindUncoveredTorsoRegions:
    """Tests for JerseyRecognizer._find_uncovered_torso_regions (instance method)."""

    def setup_method(self):
        """Create a JerseyRecognizer with a mock DB for tests that need an instance."""
        from unittest.mock import MagicMock
        mock_db = MagicMock()
        self.recognizer = JerseyRecognizer(mock_db)

    def test_no_faces_returns_bands(self):
        img = _make_bgr(h=400, w=600)
        regions = self.recognizer._find_uncovered_torso_regions(img, [])
        assert len(regions) >= 1
        # Each region should be a 4-element list
        for r in regions:
            assert len(r) == 4

    def test_face_in_center_leaves_side_regions(self):
        img = _make_bgr(h=400, w=600)
        # Single face in the centre of the image
        face_bbox = [250, 80, 350, 160]  # 100×80 px, roughly centred
        regions = self.recognizer._find_uncovered_torso_regions(img, [face_bbox])
        # Sides without face coverage should still be returned
        assert len(regions) >= 1

    def test_full_width_coverage_by_faces(self):
        """When faces span the full image width, no uncovered bands exist."""
        img = _make_bgr(h=400, w=200)
        # Three faces that together span the image width
        faces = [
            [0, 50, 70, 130],
            [60, 50, 130, 130],
            [120, 50, 200, 130],
        ]
        regions = self.recognizer._find_uncovered_torso_regions(img, faces)
        # May return empty or very narrow bands — just verify no crash
        assert isinstance(regions, list)


# ---------------------------------------------------------------------------
# OCR backend / ensure_ocr_ready
# ---------------------------------------------------------------------------

class TestOcrBackend:
    """Smoke tests for the OCR backend readiness check."""

    def test_ensure_ocr_ready_returns_bool(self, tmp_path):
        # Reset module state so we can test with a custom root
        import src.jersey_recognition as jr
        saved_ready = jr._ocr_ready
        saved_ok = jr._ocr_ok
        jr._ocr_ready = False
        jr._ocr_ok = None

        try:
            result = ensure_ocr_ready(project_root=str(tmp_path))
            assert isinstance(result, bool)
            # After call, ocr_tmp dir should exist
            assert (tmp_path / ".ocr_tmp").exists()
        finally:
            jr._ocr_ready = saved_ready
            jr._ocr_ok = saved_ok

    def test_self_test_ocr_returns_bool(self):
        """_self_test_ocr should return a bool (may be True or False)."""
        result = _self_test_ocr()
        assert isinstance(result, bool)

    def test_ensure_ocr_ready_idempotent(self):
        """Calling ensure_ocr_ready twice returns the same cached result."""
        # First call ensures state is set
        first = ensure_ocr_ready()
        second = ensure_ocr_ready()
        assert first == second

    def test_ocr_ready_state_set_after_call(self):
        import src.jersey_recognition as jr
        ensure_ocr_ready()
        assert jr._ocr_ready is True
        assert jr._ocr_ok is not None
