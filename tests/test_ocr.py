import pytest
from pathlib import Path
from src.ocr import OCREngine
from src.db import Database

@pytest.fixture
def test_ocr_engine():
    """Create an OCR engine with in-memory test database."""
    db = Database(":memory:")
    db.init_schema()
    engine = OCREngine(db)
    return engine, db

def test_ocr_engine_initialization(test_ocr_engine):
    """Verify OCR engine initializes."""
    engine, db = test_ocr_engine
    assert engine.db is not None

def test_extract_jersey_from_text():
    """Test jersey number extraction from raw OCR text."""
    engine = OCREngine(Database(":memory:"))

    # Test cases: (input_text, expected_jerseys)
    test_cases = [
        ("23", ["23"]),
        ("The player #42 runs", ["42"]),
        ("23 and 15", ["23", "15"]),
        ("no numbers here", []),
        ("234", []),  # Too many digits
        ("1", ["1"]),  # Single digit
    ]

    for text, expected in test_cases:
        result = engine._extract_jerseys_from_text(text)
        assert result == expected, f"Failed for '{text}': got {result}, expected {expected}"
