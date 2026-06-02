import pytest
import cv2
import numpy as np
from src.face_detector import FaceDetector

@pytest.fixture
def detector():
    """Initialize face detector."""
    detector = FaceDetector()
    yield detector

@pytest.fixture
def synthetic_face_image(tmp_path):
    """Create a synthetic image with a face-like region for sharpness/size testing."""
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    # Draw a high-contrast face-like rectangle so Laplacian has edges to measure
    cv2.rectangle(img, (200, 150), (440, 330), (220, 200, 180), -1)
    cv2.rectangle(img, (200, 150), (440, 330), (0, 0, 0), 3)
    path = tmp_path / "synthetic.jpg"
    cv2.imwrite(str(path), img)
    return str(path), img

def test_detector_initialization(detector):
    """Verify detector initializes."""
    assert detector is not None
    assert detector.model is not None

def test_detect_faces_empty(detector, tmp_path):
    """Test detection on invalid image returns empty."""
    fake_img = tmp_path / "blank.jpg"
    fake_img.write_bytes(b"not a real image")

    faces = detector.detect_faces(str(fake_img))
    assert isinstance(faces, list)

def test_detect_faces_returns_sharpness_key(detector, tmp_path):
    """Each face dict must contain a 'sharpness' key."""
    # Patch detect_faces to inject a fake result so we don't need InsightFace to fire
    from unittest.mock import patch, MagicMock
    import numpy as np

    fake_face = MagicMock()
    fake_face.bbox = np.array([10.0, 20.0, 110.0, 120.0])
    fake_face.embedding = np.zeros(384)
    fake_face.det_score = 0.9
    fake_face.age = 25
    fake_face.gender = "M"

    img_path = tmp_path / "test.jpg"
    img = np.ones((300, 400, 3), dtype=np.uint8) * 128
    cv2.imwrite(str(img_path), img)

    with patch.object(detector.app, "get", return_value=[fake_face]):
        faces = detector.detect_faces(str(img_path))

    assert "sharpness" in faces[0]

def test_detect_faces_returns_face_size_ratio_key(detector, tmp_path):
    """Each face dict must contain a 'face_size_ratio' key."""
    from unittest.mock import patch, MagicMock

    fake_face = MagicMock()
    fake_face.bbox = np.array([10.0, 20.0, 110.0, 120.0])
    fake_face.embedding = np.zeros(384)
    fake_face.det_score = 0.9
    fake_face.age = 25
    fake_face.gender = "M"

    img_path = tmp_path / "test.jpg"
    img = np.ones((300, 400, 3), dtype=np.uint8) * 128
    cv2.imwrite(str(img_path), img)

    with patch.object(detector.app, "get", return_value=[fake_face]):
        faces = detector.detect_faces(str(img_path))

    assert "face_size_ratio" in faces[0]

def test_sharpness_is_non_negative(detector, tmp_path):
    """Sharpness (Laplacian variance) must be >= 0."""
    from unittest.mock import patch, MagicMock

    fake_face = MagicMock()
    fake_face.bbox = np.array([10.0, 20.0, 110.0, 120.0])
    fake_face.embedding = np.zeros(384)
    fake_face.det_score = 0.9
    fake_face.age = 25
    fake_face.gender = "M"

    img_path = tmp_path / "test.jpg"
    img = np.ones((300, 400, 3), dtype=np.uint8) * 128
    cv2.imwrite(str(img_path), img)

    with patch.object(detector.app, "get", return_value=[fake_face]):
        faces = detector.detect_faces(str(img_path))

    assert faces[0]["sharpness"] >= 0.0

def test_face_size_ratio_between_zero_and_one(detector, tmp_path):
    """face_size_ratio must be in [0, 1]."""
    from unittest.mock import patch, MagicMock

    fake_face = MagicMock()
    fake_face.bbox = np.array([10.0, 20.0, 110.0, 120.0])  # 100x100 face
    fake_face.embedding = np.zeros(384)
    fake_face.det_score = 0.9
    fake_face.age = 25
    fake_face.gender = "M"

    img_path = tmp_path / "test.jpg"
    img = np.ones((300, 400, 3), dtype=np.uint8) * 128  # 400x300 image
    cv2.imwrite(str(img_path), img)

    with patch.object(detector.app, "get", return_value=[fake_face]):
        faces = detector.detect_faces(str(img_path))

    assert 0.0 <= faces[0]["face_size_ratio"] <= 1.0

def test_face_size_ratio_reflects_bbox_area(detector, tmp_path):
    """face_size_ratio should equal bbox_area / image_area."""
    from unittest.mock import patch, MagicMock

    # 100x100 bbox in 400x300 image → ratio = 10000/120000 ≈ 0.0833
    fake_face = MagicMock()
    fake_face.bbox = np.array([0.0, 0.0, 100.0, 100.0])
    fake_face.embedding = np.zeros(384)
    fake_face.det_score = 0.9
    fake_face.age = 25
    fake_face.gender = "M"

    img_path = tmp_path / "test.jpg"
    img = np.ones((300, 400, 3), dtype=np.uint8) * 128
    cv2.imwrite(str(img_path), img)

    with patch.object(detector.app, "get", return_value=[fake_face]):
        faces = detector.detect_faces(str(img_path))

    expected = (100 * 100) / (400 * 300)
    assert abs(faces[0]["face_size_ratio"] - expected) < 0.001

def test_sharp_crop_has_higher_sharpness_than_flat(detector, tmp_path):
    """A high-contrast face crop should produce higher sharpness than a flat one."""
    from unittest.mock import patch, MagicMock

    # Flat (all grey) image → low Laplacian variance
    flat_img = np.ones((300, 400, 3), dtype=np.uint8) * 128
    flat_path = tmp_path / "flat.jpg"
    cv2.imwrite(str(flat_path), flat_img)

    # Sharp (checkerboard) image → high Laplacian variance
    sharp_img = np.zeros((300, 400, 3), dtype=np.uint8)
    sharp_img[::4, :] = 255
    sharp_path = tmp_path / "sharp.jpg"
    cv2.imwrite(str(sharp_path), sharp_img)

    fake_face = MagicMock()
    fake_face.bbox = np.array([50.0, 50.0, 200.0, 200.0])
    fake_face.embedding = np.zeros(384)
    fake_face.det_score = 0.9
    fake_face.age = 25
    fake_face.gender = "M"

    with patch.object(detector.app, "get", return_value=[fake_face]):
        flat_faces = detector.detect_faces(str(flat_path))
        sharp_faces = detector.detect_faces(str(sharp_path))

    assert sharp_faces[0]["sharpness"] > flat_faces[0]["sharpness"]
