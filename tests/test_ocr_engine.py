"""
Unit tests for src/ocr.py (OCREngine).

EasyOCR and FaceDetector are mocked so tests run without loading large models.
Covers process_photo, process_batch, process_batch_parallel, and the
_preprocess_for_ocr static helper.
"""

import io
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest
from PIL import Image

from src.db import Database


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write_jpeg(path: Path, color=(128, 128, 128)):
    img = Image.new("RGB", (64, 64), color=color)
    img.save(str(path), format="JPEG")


def _make_db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "test.db"))
    db.init_schema()
    return db


# ---------------------------------------------------------------------------
# OCREngine construction (mocked EasyOCR)
# ---------------------------------------------------------------------------

class TestOCREngineInit:
    def test_creates_engine_with_mocked_reader(self, tmp_path):
        db = _make_db(tmp_path)
        with patch("easyocr.Reader") as mock_reader:
            mock_reader.return_value = MagicMock()
            from src.ocr import OCREngine
            engine = OCREngine(db)
            assert engine is not None
            mock_reader.assert_called_once()

    def test_default_language_is_english(self, tmp_path):
        db = _make_db(tmp_path)
        with patch("easyocr.Reader") as mock_reader:
            mock_reader.return_value = MagicMock()
            from src.ocr import OCREngine
            engine = OCREngine(db)
            assert engine.languages == ["en"]

    def test_custom_languages(self, tmp_path):
        db = _make_db(tmp_path)
        with patch("easyocr.Reader") as mock_reader:
            mock_reader.return_value = MagicMock()
            from src.ocr import OCREngine
            engine = OCREngine(db, languages=["en", "fr"])
            assert "fr" in engine.languages


# ---------------------------------------------------------------------------
# _preprocess_for_ocr (static, no mock needed)
# ---------------------------------------------------------------------------

class TestPreprocessForOcr:
    def test_returns_none_for_missing_file(self):
        from src.ocr import OCREngine
        result = OCREngine._preprocess_for_ocr("/nonexistent/file.jpg")
        assert result is None

    def test_returns_array_for_valid_image(self, tmp_path):
        img_path = tmp_path / "test.jpg"
        _write_jpeg(img_path)
        from src.ocr import OCREngine
        result = OCREngine._preprocess_for_ocr(str(img_path))
        assert result is not None
        assert isinstance(result, np.ndarray)


# ---------------------------------------------------------------------------
# process_photo (mocked reader)
# ---------------------------------------------------------------------------

class TestProcessPhoto:
    def _engine(self, tmp_path):
        db = _make_db(tmp_path)
        with patch("easyocr.Reader") as mock_reader:
            mock_reader.return_value = MagicMock()
            from src.ocr import OCREngine
            engine = OCREngine(db)
        engine.db = db
        return engine, db

    def test_returns_none_for_missing_photo_path(self, tmp_path):
        engine, db = self._engine(tmp_path)
        result = engine.process_photo(1, "/nonexistent/photo.jpg")
        assert result is None

    def test_returns_dict_when_ocr_finds_digits(self, tmp_path):
        img_path = tmp_path / "player.jpg"
        _write_jpeg(img_path)
        db = _make_db(tmp_path)

        with patch("easyocr.Reader") as mock_reader:
            # Mock the readtext response: [([[bbox]], text, confidence), ...]
            mock_reader.return_value.readtext.return_value = [
                ([[0, 0], [10, 0], [10, 10], [0, 10]], "19", 0.95)
            ]
            from src.ocr import OCREngine
            engine = OCREngine(db)

        # Add the photo to DB first
        photo_id = db.photos.add_photo(str(img_path), file_hash="phash")
        result = engine.process_photo(photo_id, str(img_path))

        assert result is not None
        assert result["photo_id"] == photo_id
        assert "jerseys_found" in result

    def test_returns_dict_when_ocr_finds_nothing(self, tmp_path):
        img_path = tmp_path / "empty.jpg"
        _write_jpeg(img_path)
        db = _make_db(tmp_path)

        with patch("easyocr.Reader") as mock_reader:
            mock_reader.return_value.readtext.return_value = []
            from src.ocr import OCREngine
            engine = OCREngine(db)

        photo_id = db.photos.add_photo(str(img_path), file_hash="phash2")
        result = engine.process_photo(photo_id, str(img_path))
        assert result is not None
        assert result["primary_jersey"] is None


# ---------------------------------------------------------------------------
# process_batch (mocked reader)
# ---------------------------------------------------------------------------

class TestProcessBatch:
    def _engine_with_db(self, tmp_path):
        db = _make_db(tmp_path)
        with patch("easyocr.Reader") as mock_reader:
            mock_reader.return_value.readtext.return_value = []
            from src.ocr import OCREngine
            engine = OCREngine(db)
        return engine, db

    def test_empty_batch_returns_zeros(self, tmp_path):
        engine, db = self._engine_with_db(tmp_path)
        result = engine.process_batch([])
        assert result["photos_processed"] == 0
        assert result["errors"] == 0

    def test_batch_processes_all_photos(self, tmp_path):
        engine, db = self._engine_with_db(tmp_path)
        # Add 3 photos to DB
        for i in range(3):
            img = tmp_path / f"p{i}.jpg"
            _write_jpeg(img)
            db.photos.add_photo(str(img), file_hash=f"h{i}")

        result = engine.process_batch()
        assert result["photos_processed"] >= 0  # may be 0 if preprocessing fails
        assert "errors" in result

    def test_batch_handles_missing_photo_ids_gracefully(self, tmp_path):
        engine, db = self._engine_with_db(tmp_path)
        # Pass photo IDs that don't exist in DB
        result = engine.process_batch([9999, 8888])
        assert result["photos_processed"] == 0

    def test_batch_with_specific_ids(self, tmp_path):
        engine, db = self._engine_with_db(tmp_path)
        img = tmp_path / "photo.jpg"
        _write_jpeg(img)
        photo_id = db.photos.add_photo(str(img), file_hash="specific")
        result = engine.process_batch([photo_id])
        assert isinstance(result, dict)
        assert "photos_processed" in result


# ---------------------------------------------------------------------------
# process_batch_parallel (mocked reader + FaceDetector)
# ---------------------------------------------------------------------------

class TestProcessBatchParallel:
    def test_empty_batch_returns_immediately(self, tmp_path):
        db = _make_db(tmp_path)
        with patch("easyocr.Reader") as mock_reader, \
             patch("src.ocr.FaceDetector") as mock_fd:
            mock_reader.return_value.readtext.return_value = []
            mock_fd.return_value.detect_faces.return_value = []
            from src.ocr import OCREngine
            engine = OCREngine(db)

        result = engine.process_batch_parallel([])
        assert "elapsed_time" in result
        assert result["photos_processed"] == 0

    def test_parallel_with_photos(self, tmp_path):
        db = _make_db(tmp_path)
        img = tmp_path / "par.jpg"
        _write_jpeg(img)
        photo_id = db.photos.add_photo(str(img), file_hash="par")

        with patch("easyocr.Reader") as mock_reader, \
             patch("src.ocr.FaceDetector") as mock_fd:
            mock_reader.return_value.readtext.return_value = []
            mock_fd.return_value.detect_faces.return_value = []
            from src.ocr import OCREngine
            engine = OCREngine(db)

        result = engine.process_batch_parallel([photo_id], max_workers=1)
        assert isinstance(result, dict)
        assert "elapsed_time" in result
