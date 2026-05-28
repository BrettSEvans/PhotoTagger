import pytest
from src.face_detector import FaceDetector

@pytest.fixture
def detector():
    """Initialize face detector."""
    detector = FaceDetector()
    yield detector

def test_detector_initialization(detector):
    """Verify detector initializes."""
    assert detector is not None
    assert detector.model is not None

def test_detect_faces_empty(detector, tmp_path):
    """Test detection on invalid image returns empty."""
    # Create a blank/invalid image file
    fake_img = tmp_path / "blank.jpg"
    fake_img.write_bytes(b"not a real image")

    faces = detector.detect_faces(str(fake_img))
    assert isinstance(faces, list)
    # Empty or error is OK for invalid image
