import pytest
from pathlib import Path
from src.crawler import PhotoCrawler
from src.db import Database

@pytest.fixture
def test_crawler(tmp_path):
    """Create a crawler with in-memory test database."""
    db = Database(":memory:")
    db.init_schema()
    crawler = PhotoCrawler(db)
    return crawler, db, tmp_path

def test_crawler_initialization(test_crawler):
    """Verify crawler initializes with a database."""
    crawler, db, _ = test_crawler
    assert crawler.db is not None

def test_crawl_empty_directory(test_crawler):
    """Crawling an empty directory should return 0 photos."""
    crawler, db, tmp_path = test_crawler
    results = crawler.crawl(str(tmp_path))
    assert results["photos_found"] == 0
    assert results["photos_ingested"] == 0

def test_crawl_with_photos(test_crawler):
    """Crawling a directory with photos should ingest them."""
    crawler, db, tmp_path = test_crawler

    # Create 3 dummy photo files with unique content
    for i in range(3):
        photo = tmp_path / f"photo{i}.jpg"
        photo.write_bytes(f"fake jpg data {i}".encode())

    results = crawler.crawl(str(tmp_path))
    assert results["photos_found"] == 3
    assert results["photos_ingested"] == 3

    # Verify they're in the database
    all_photos = db.get_all_photos()
    assert len(all_photos) == 3

def test_duplicate_detection(test_crawler):
    """Crawler should skip photos already in the database."""
    crawler, db, tmp_path = test_crawler

    # Create one photo file
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"identical data")

    # Crawl once
    results1 = crawler.crawl(str(tmp_path))
    assert results1["photos_ingested"] == 1
    assert results1["duplicates_skipped"] == 0

    # Crawl again (same photo, same hash)
    results2 = crawler.crawl(str(tmp_path))
    assert results2["photos_ingested"] == 0
    assert results2["duplicates_skipped"] == 1
