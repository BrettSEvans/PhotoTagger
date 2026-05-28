import pytest
from src.ocr import OCREngine
from src.db import Database
from src.config import get_optimal_worker_count

def test_optimal_worker_count():
    """Test worker count calculation."""
    workers = get_optimal_worker_count()
    assert isinstance(workers, int)
    assert workers >= 1

def test_parallel_batch_ocr_empty(tmp_path):
    """Test parallel processing with no photos."""
    db = Database(":memory:")
    db.init_schema()
    engine = OCREngine(db)

    results = engine.process_batch_parallel(max_workers=2)
    assert results["photos_processed"] == 0
    assert results["errors"] == 0
