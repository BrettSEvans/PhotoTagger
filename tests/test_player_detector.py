import pytest
from pathlib import Path
from src.player_detector import PlayerDetector
from src.db import Database


@pytest.fixture
def detector():
    """Initialize PlayerDetector."""
    return PlayerDetector()


@pytest.fixture
def photo_path():
    """Get path to test photo."""
    return "photos/DSC_0256-sm.JPG"


class TestPlayerDetectorInitialization:
    """Test PlayerDetector initialization."""

    def test_detector_initializes(self, detector):
        """PlayerDetector should initialize with FaceAnalysis."""
        assert detector.initialized is True
        assert detector.face_detector is not None

    def test_detector_has_methods(self, detector):
        """PlayerDetector should have required methods."""
        assert hasattr(detector, 'detect_players')
        assert hasattr(detector, 'filter_field_players')
        assert hasattr(detector, 'filter_by_location')
        assert callable(detector.detect_players)


class TestPlayerDetectionBasics:
    """Test basic player detection."""

    def test_detect_players_valid_image(self, detector, photo_path):
        """detect_players should return list of detected people."""
        if not Path(photo_path).exists():
            pytest.skip("Test photo not available")

        result = detector.detect_players(photo_path)

        assert result is not None
        assert isinstance(result, list)
        assert len(result) > 0

        # Check structure of first detection
        person = result[0]
        assert 'face_id' in person
        assert 'bbox' in person
        assert 'bbox_expanded' in person
        assert 'location' in person
        assert 'location_confidence' in person
        assert 'embedding' in person

    def test_detect_players_missing_image(self, detector):
        """detect_players should return None for missing image."""
        result = detector.detect_players("photos/nonexistent.jpg")
        assert result is None

    def test_detect_players_empty_image(self, detector):
        """detect_players should handle images with no faces."""
        # Create a temporary blank image
        import cv2
        import tempfile
        import numpy as np

        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            blank = np.ones((100, 100, 3), dtype=np.uint8) * 255
            cv2.imwrite(f.name, blank)

            result = detector.detect_players(f.name)
            assert result == []


class TestLocationClassification:
    """Test location classification logic."""

    def test_location_classification_field(self, detector):
        """Faces in upper 70% should be classified as field."""
        location, confidence = detector._classify_location(0.35, 1000)
        assert location == 'field'
        assert 0.7 <= confidence <= 1.0

    def test_location_classification_sideline(self, detector):
        """Faces between 70-85% should be classified as sideline."""
        location, confidence = detector._classify_location(0.77, 1000)
        assert location == 'sideline'
        assert 0.5 <= confidence <= 0.7

    def test_location_classification_background(self, detector):
        """Faces in bottom 15% should be classified as background."""
        location, confidence = detector._classify_location(0.90, 1000)
        assert location == 'background'
        assert 0.65 <= confidence <= 1.0

    def test_location_classification_boundary_field_sideline(self, detector):
        """Boundary at 0.70 should classify as sideline."""
        location, _ = detector._classify_location(0.70, 1000)
        assert location == 'sideline'

    def test_location_classification_boundary_sideline_background(self, detector):
        """Boundary at 0.85 should classify as background."""
        location, _ = detector._classify_location(0.85, 1000)
        assert location == 'background'


class TestFieldPlayerFiltering:
    """Test field player filtering."""

    def test_filter_field_players_removes_background(self, detector):
        """filter_field_players should only keep field locations."""
        people = [
            {'face_id': 0, 'location': 'field'},
            {'face_id': 1, 'location': 'sideline'},
            {'face_id': 2, 'location': 'background'},
            {'face_id': 3, 'location': 'field'},
        ]

        result = detector.filter_field_players(people)

        assert len(result) == 2
        assert result[0]['face_id'] == 0
        assert result[1]['face_id'] == 3

    def test_filter_field_players_empty(self, detector):
        """filter_field_players should handle empty input."""
        result = detector.filter_field_players([])
        assert result == []

    def test_filter_by_location_sideline(self, detector):
        """filter_by_location should filter to specific location."""
        people = [
            {'face_id': 0, 'location': 'field'},
            {'face_id': 1, 'location': 'sideline'},
            {'face_id': 2, 'location': 'background'},
        ]

        result = detector.filter_by_location(people, 'sideline')

        assert len(result) == 1
        assert result[0]['face_id'] == 1

    def test_filter_by_location_all_locations(self, detector):
        """filter_by_location should work for all location types."""
        people = [
            {'face_id': 0, 'location': 'field'},
            {'face_id': 1, 'location': 'sideline'},
            {'face_id': 2, 'location': 'background'},
        ]

        for location in ['field', 'sideline', 'background']:
            result = detector.filter_by_location(people, location)
            assert len(result) == 1
            assert result[0]['location'] == location


class TestBboxExpansion:
    """Test bounding box expansion for body region."""

    def test_bbox_expanded_covers_body(self, detector, photo_path):
        """bbox_expanded should be larger than face bbox."""
        if not Path(photo_path).exists():
            pytest.skip("Test photo not available")

        result = detector.detect_players(photo_path)

        for person in result:
            x0, y0, x1, y1 = person['bbox']
            ex0, ey0, ex1, ey1 = person['bbox_expanded']

            # Expanded should be larger
            face_area = (x1 - x0) * (y1 - y0)
            body_area = (ex1 - ex0) * (ey1 - ey0)
            assert body_area > face_area

            # Expanded should contain face
            assert ex0 <= x0
            assert ey0 <= y0
            assert ex1 >= x1
            assert ey1 >= y1


class TestDetectionQuantity:
    """Test detection quantity on real photo."""

    def test_detect_multiple_people(self, detector, photo_path):
        """Should detect multiple people in group photo."""
        if not Path(photo_path).exists():
            pytest.skip("Test photo not available")

        result = detector.detect_players(photo_path)

        # Tournament photo should have multiple people
        assert len(result) >= 3

        # All should be classified with some location
        for person in result:
            assert person['location'] in ['field', 'sideline', 'background']
            assert 0.0 <= person['location_confidence'] <= 1.0


class TestEmbeddings:
    """Test face embedding extraction."""

    def test_embedding_dimension(self, detector, photo_path):
        """Face embeddings should be 512-dimensional (buffalo_l model)."""
        if not Path(photo_path).exists():
            pytest.skip("Test photo not available")

        result = detector.detect_players(photo_path)

        for person in result:
            embedding = person['embedding']
            assert embedding is not None
            assert len(embedding) == 512  # InsightFace buffalo_l uses 512-dim embeddings

    def test_embedding_is_vector(self, detector, photo_path):
        """Embeddings should be numeric vectors."""
        if not Path(photo_path).exists():
            pytest.skip("Test photo not available")

        result = detector.detect_players(photo_path)

        for person in result:
            embedding = person['embedding']
            # Should be able to compute magnitude
            magnitude = (embedding ** 2).sum() ** 0.5
            assert magnitude > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
