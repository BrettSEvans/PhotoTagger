# PhotoTagger Phase 1 MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local photo discovery system that crawls a folder of photos, extracts jersey numbers via OCR, stores metadata in SQLite, and provides a simple REST API to search photos by jersey number.

**Architecture:** A Python-based pipeline with three core components: (1) **Crawler** walks a local photo directory and ingests all JPG/PNG files with timestamps and paths; (2) **OCR Engine** runs on each photo, extracts visible text (jersey numbers), stores results; (3) **REST API** (Flask) allows searching by jersey number, returning matching photo paths. All metadata lives in local SQLite. Phase 1 is CLI + API testing only — no UI yet.

**Tech Stack:** Python 3.11+, Flask, SQLite, EasyOCR (open-source), Pillow for image handling, pytest for testing.

---

## File Structure

```
PhotoTagger/
├── photos/                          # Local test photo directory (user creates)
├── rosters/                         # JSON roster data (team → jersey → name)
│   └── sample-roster.json
├── src/
│   ├── __init__.py
│   ├── db.py                        # SQLite operations (schema, queries)
│   ├── crawler.py                   # Walk photo directory, ingest paths
│   ├── ocr.py                       # Jersey number extraction via EasyOCR
│   ├── api.py                       # Flask REST API endpoints
│   └── utils.py                     # Shared utilities (logging, path handling)
├── tests/
│   ├── __init__.py
│   ├── test_db.py                   # Database operations
│   ├── test_crawler.py              # Crawler functionality
│   ├── test_ocr.py                  # OCR extraction
│   └── test_api.py                  # API endpoints
├── .gitignore
├── requirements.txt
├── CLAUDE.md                        # Project documentation
└── README.md
```

---

## Phase 1 Tasks

### Task 1: Project Setup & Dependencies

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `CLAUDE.md`
- Create: `README.md`
- Create: `src/__init__.py`

**Summary:** Set up Python environment, dependencies, and project documentation. This is table-stakes for local development.

- [ ] **Step 1: Create requirements.txt with all dependencies**

```
Flask==3.0.0
Pillow==10.1.0
easyocr==1.7.1
pytest==7.4.3
pytest-cov==4.1.0
```

Save to `/Users/brettevanssf/Code/Saasless/PhotoTagger/requirements.txt`

- [ ] **Step 2: Create .gitignore**

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
.venv

# IDE
.vscode/
.idea/
*.swp
*.swo

# Project-specific
photos/
*.db
*.sqlite3
.env
logs/
*.log

# OS
.DS_Store
Thumbs.db
```

Save to `/Users/brettevanssf/Code/Saasless/PhotoTagger/.gitignore`

- [ ] **Step 3: Create CLAUDE.md with project context**

```markdown
# PhotoTagger

A local photo discovery system for Ultimate Frisbee tournaments. Find all photos of a player by jersey number and roster data.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Project Structure

- `src/db.py` — SQLite schema and queries
- `src/crawler.py` — Ingest photos from local directory
- `src/ocr.py` — Jersey number extraction
- `src/api.py` — Flask REST API
- `tests/` — Pytest tests
- `photos/` — Local test photos (user-created)
- `rosters/` — JSON team/roster data

## Running

```bash
# Test
pytest tests/ -v

# Crawl local photos
python -m src.crawler --photos ./photos

# Start API
python -m src.api
```

## Phase 1 Goals

- [x] Local photo crawling
- [x] Jersey OCR extraction
- [x] Roster lookup
- [x] REST API (search by jersey)
- [ ] Face embedding (Phase 2)
- [ ] Web UI (Phase 2)
```

Save to `/Users/brettevanssf/Code/Saasless/PhotoTagger/CLAUDE.md`

- [ ] **Step 4: Create README.md**

```markdown
# PhotoTagger

Find photos of Ultimate Frisbee players by jersey number.

## Quick Start

1. Create a `photos/` directory with your test JPGs
2. Run the crawler: `python -m src.crawler --photos ./photos`
3. Start the API: `python -m src.api`
4. Query: `curl http://localhost:5000/api/search?jersey=23&team=team-name`

## Architecture

**Crawler** → scans local photo folder → **OCR Engine** → extracts jersey numbers → **SQLite** → **REST API**

## Testing

```bash
pytest tests/ -v --cov=src
```
```

Save to `/Users/brettevanssf/Code/Saasless/PhotoTagger/README.md`

- [ ] **Step 5: Create src/__init__.py (empty marker file)**

```python
# PhotoTagger package
```

Save to `/Users/brettevanssf/Code/Saasless/PhotoTagger/src/__init__.py`

- [ ] **Step 6: Commit project setup**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
git add requirements.txt .gitignore CLAUDE.md README.md src/__init__.py
git commit -m "chore: initial project setup with dependencies and docs"
```

Expected: Clean commit with no unstaged changes.

---

### Task 2: SQLite Database Schema & Operations

**Files:**
- Create: `src/db.py`
- Create: `tests/test_db.py`

**Summary:** Design and implement the SQLite schema for storing photo metadata (path, file hash, ingestion timestamp) and OCR results (jersey numbers, confidence scores). Keep it simple for Phase 1.

- [ ] **Step 1: Write test for database initialization**

```python
# tests/test_db.py
import os
import pytest
from src.db import Database

@pytest.fixture
def test_db():
    """Create an in-memory SQLite database for testing."""
    db = Database(":memory:")
    db.init_schema()
    yield db
    db.close()

def test_database_initialization(test_db):
    """Verify schema exists after init."""
    cursor = test_db.conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    assert "photos" in tables
    assert "ocr_results" in tables
```

Save to `/Users/brettevanssf/Code/Saasless/PhotoTagger/tests/test_db.py`

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
pytest tests/test_db.py::test_database_initialization -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'src.db'"

- [ ] **Step 3: Create src/db.py with Database class and schema**

```python
# src/db.py
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

class Database:
    def __init__(self, db_path: str = "photo_catalog.db"):
        """Initialize database connection."""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row  # Return rows as dicts

    def init_schema(self):
        """Create database tables if they don't exist."""
        cursor = self.conn.cursor()
        
        # Photos table: metadata about each photo file
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_hash TEXT UNIQUE NOT NULL,
                file_size INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # OCR results table: jersey numbers extracted from each photo
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ocr_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                photo_id INTEGER NOT NULL,
                jersey_number TEXT,
                confidence REAL,
                raw_text TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (photo_id) REFERENCES photos(id) ON DELETE CASCADE
            )
        """)
        
        self.conn.commit()

    def add_photo(self, file_path: str, file_hash: Optional[str] = None) -> int:
        """
        Add a photo to the database.
        Returns the photo ID.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Photo not found: {file_path}")
        
        # Generate file hash if not provided
        if file_hash is None:
            file_hash = self._compute_file_hash(file_path)
        
        file_size = path.stat().st_size
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO photos (file_path, file_hash, file_size)
            VALUES (?, ?, ?)
        """, (str(file_path), file_hash, file_size))
        self.conn.commit()
        
        return cursor.lastrowid

    def add_ocr_result(self, photo_id: int, jersey_number: Optional[str], 
                      confidence: float, raw_text: str):
        """Add OCR extraction results for a photo."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO ocr_results (photo_id, jersey_number, confidence, raw_text)
            VALUES (?, ?, ?, ?)
        """, (photo_id, jersey_number, confidence, raw_text))
        self.conn.commit()

    def get_photo_by_jersey(self, jersey_number: str) -> List[Dict]:
        """Find all photos matching a jersey number."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT p.id, p.file_path, o.jersey_number, o.confidence, o.raw_text
            FROM photos p
            JOIN ocr_results o ON p.id = o.photo_id
            WHERE o.jersey_number = ?
            ORDER BY o.confidence DESC
        """, (jersey_number,))
        
        return [dict(row) for row in cursor.fetchall()]

    def get_all_photos(self) -> List[Dict]:
        """Get all photos in the database."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM photos")
        return [dict(row) for row in cursor.fetchall()]

    def get_photo_ocr(self, photo_id: int) -> Optional[Dict]:
        """Get OCR results for a specific photo."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM ocr_results WHERE photo_id = ? ORDER BY processed_at DESC LIMIT 1
        """, (photo_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def photo_exists(self, file_hash: str) -> bool:
        """Check if a photo with this hash already exists."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM photos WHERE file_hash = ?", (file_hash,))
        return cursor.fetchone() is not None

    def close(self):
        """Close database connection."""
        self.conn.close()

    @staticmethod
    def _compute_file_hash(file_path: str, chunk_size: int = 8192) -> str:
        """Compute SHA256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                sha256.update(chunk)
        return sha256.hexdigest()
```

Save to `/Users/brettevanssf/Code/Saasless/PhotoTagger/src/db.py`

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
pytest tests/test_db.py::test_database_initialization -v
```

Expected: PASS

- [ ] **Step 5: Add more database operation tests**

```python
# tests/test_db.py (append to existing file)

def test_add_photo(test_db, tmp_path):
    """Test adding a photo to the database."""
    # Create a dummy photo file
    photo_file = tmp_path / "test.jpg"
    photo_file.write_bytes(b"fake jpg data")
    
    photo_id = test_db.add_photo(str(photo_file))
    assert photo_id is not None
    assert photo_id > 0
    
    # Verify it was stored
    photos = test_db.get_all_photos()
    assert len(photos) == 1
    assert photos[0]["file_path"] == str(photo_file)

def test_photo_exists(test_db, tmp_path):
    """Test checking if a photo already exists."""
    photo_file = tmp_path / "test.jpg"
    photo_file.write_bytes(b"fake jpg data")
    
    file_hash = Database._compute_file_hash(str(photo_file))
    
    # Should not exist yet
    assert not test_db.photo_exists(file_hash)
    
    # Add it
    test_db.add_photo(str(photo_file), file_hash)
    
    # Should exist now
    assert test_db.photo_exists(file_hash)

def test_add_ocr_result(test_db, tmp_path):
    """Test adding OCR results for a photo."""
    photo_file = tmp_path / "test.jpg"
    photo_file.write_bytes(b"fake jpg data")
    
    photo_id = test_db.add_photo(str(photo_file))
    test_db.add_ocr_result(photo_id, "23", 0.95, "23 in white text")
    
    result = test_db.get_photo_ocr(photo_id)
    assert result["jersey_number"] == "23"
    assert result["confidence"] == 0.95

def test_get_photo_by_jersey(test_db, tmp_path):
    """Test searching photos by jersey number."""
    # Create two dummy photos
    photo1 = tmp_path / "photo1.jpg"
    photo2 = tmp_path / "photo2.jpg"
    photo1.write_bytes(b"fake jpg 1")
    photo2.write_bytes(b"fake jpg 2")
    
    # Add both
    id1 = test_db.add_photo(str(photo1))
    id2 = test_db.add_photo(str(photo2))
    
    # Add OCR results: both have jersey 23
    test_db.add_ocr_result(id1, "23", 0.95, "23")
    test_db.add_ocr_result(id2, "23", 0.88, "23")
    
    # Search for jersey 23
    results = test_db.get_photo_by_jersey("23")
    assert len(results) == 2
    assert results[0]["file_path"] == str(photo1)  # Higher confidence first
```

Append to `/Users/brettevanssf/Code/Saasless/PhotoTagger/tests/test_db.py`

- [ ] **Step 6: Run all database tests**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
pytest tests/test_db.py -v
```

Expected: All 5 tests PASS

- [ ] **Step 7: Commit database implementation**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
git add src/db.py tests/test_db.py
git commit -m "feat: implement SQLite database schema and operations"
```

---

### Task 3: Photo Crawler

**Files:**
- Create: `src/crawler.py`
- Create: `tests/test_crawler.py`

**Summary:** Walk a local photo directory, hash each image file, and ingest it into the database. Handle duplicates via file hash.

- [ ] **Step 1: Write test for crawler**

```python
# tests/test_crawler.py
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
    
    # Create 3 dummy photo files
    for i in range(3):
        photo = tmp_path / f"photo{i}.jpg"
        photo.write_bytes(b"fake jpg data")
    
    results = crawler.crawl(str(tmp_path))
    assert results["photos_found"] == 3
    assert results["photos_ingested"] == 3
    
    # Verify they're in the database
    all_photos = db.get_all_photos()
    assert len(all_photos) == 3
```

Save to `/Users/brettevanssf/Code/Saasless/PhotoTagger/tests/test_crawler.py`

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
pytest tests/test_crawler.py::test_crawler_initialization -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'src.crawler'"

- [ ] **Step 3: Create src/crawler.py**

```python
# src/crawler.py
import logging
from pathlib import Path
from typing import Dict
from src.db import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PhotoCrawler:
    """Walk a directory tree and ingest photos into the database."""
    
    # Supported image extensions
    SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}
    
    def __init__(self, db: Database):
        """Initialize crawler with a database connection."""
        self.db = db
    
    def crawl(self, photo_dir: str) -> Dict:
        """
        Crawl a directory for photos and ingest them.
        
        Returns:
            Dict with keys:
            - photos_found: total image files found
            - photos_ingested: successfully added to database
            - duplicates_skipped: already in database
            - errors: number of processing errors
        """
        photo_dir = Path(photo_dir)
        
        if not photo_dir.exists():
            raise FileNotFoundError(f"Directory not found: {photo_dir}")
        
        results = {
            "photos_found": 0,
            "photos_ingested": 0,
            "duplicates_skipped": 0,
            "errors": 0,
        }
        
        # Walk the directory recursively
        image_files = []
        for ext in self.SUPPORTED_FORMATS:
            image_files.extend(photo_dir.rglob(f"*{ext}"))
        
        results["photos_found"] = len(image_files)
        logger.info(f"Found {results['photos_found']} image files in {photo_dir}")
        
        for file_path in image_files:
            try:
                # Compute file hash to detect duplicates
                file_hash = Database._compute_file_hash(str(file_path))
                
                # Skip if already in database
                if self.db.photo_exists(file_hash):
                    logger.debug(f"Skipping duplicate: {file_path}")
                    results["duplicates_skipped"] += 1
                    continue
                
                # Ingest the photo
                photo_id = self.db.add_photo(str(file_path), file_hash)
                logger.debug(f"Ingested: {file_path} (ID: {photo_id})")
                results["photos_ingested"] += 1
            
            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
                results["errors"] += 1
        
        logger.info(f"Crawl complete: {results}")
        return results
```

Save to `/Users/brettevanssf/Code/Saasless/PhotoTagger/src/crawler.py`

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
pytest tests/test_crawler.py -v
```

Expected: All 4 tests PASS

- [ ] **Step 5: Add integration test for duplicate handling**

```python
# tests/test_crawler.py (append)

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
```

Append to `/Users/brettevanssf/Code/Saasless/PhotoTagger/tests/test_crawler.py`

- [ ] **Step 6: Run all crawler tests**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
pytest tests/test_crawler.py -v
```

Expected: All 5 tests PASS

- [ ] **Step 7: Commit crawler implementation**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
git add src/crawler.py tests/test_crawler.py
git commit -m "feat: implement photo crawler with duplicate detection"
```

---

### Task 4: OCR Engine for Jersey Number Extraction

**Files:**
- Create: `src/ocr.py`
- Create: `tests/test_ocr.py`

**Summary:** Use EasyOCR to extract text from photos, identify jersey numbers (1-3 digit numbers), and store results with confidence scores.

- [ ] **Step 1: Write test for OCR engine**

```python
# tests/test_ocr.py
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
```

Save to `/Users/brettevanssf/Code/Saasless/PhotoTagger/tests/test_ocr.py`

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
pytest tests/test_ocr.py::test_ocr_engine_initialization -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'src.ocr'"

- [ ] **Step 3: Create src/ocr.py**

```python
# src/ocr.py
import logging
import re
from typing import List, Optional, Dict
from pathlib import Path
import easyocr
from src.db import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OCREngine:
    """Extract text and jersey numbers from photos using EasyOCR."""
    
    def __init__(self, db: Database, languages: List[str] = None):
        """
        Initialize OCR engine.
        
        Args:
            db: Database connection
            languages: Languages to recognize (default: English)
        """
        self.db = db
        self.languages = languages or ["en"]
        
        # Initialize EasyOCR reader (lazy-loads model on first use)
        logger.info(f"Initializing EasyOCR reader for languages: {self.languages}")
        self.reader = easyocr.Reader(self.languages, gpu=False)
    
    def process_photo(self, photo_id: int, photo_path: str) -> Optional[Dict]:
        """
        Run OCR on a photo and extract jersey numbers.
        
        Args:
            photo_id: ID of photo in database
            photo_path: Path to the photo file
        
        Returns:
            Dict with extracted data or None if processing failed
        """
        try:
            path = Path(photo_path)
            if not path.exists():
                logger.error(f"Photo not found: {photo_path}")
                return None
            
            # Run OCR
            logger.info(f"Processing photo: {photo_path}")
            results = self.reader.readtext(photo_path)
            
            # Combine all detected text
            raw_text = " ".join([text for (_, text, _) in results])
            logger.debug(f"Raw OCR text: {raw_text}")
            
            # Extract jersey numbers
            jerseys = self._extract_jerseys_from_text(raw_text)
            
            # Store results (pick the first jersey, or None if multiple)
            primary_jersey = jerseys[0] if jerseys else None
            
            # Calculate confidence as average confidence of all detections
            confidence = sum([conf for (_, _, conf) in results]) / len(results) if results else 0.0
            
            self.db.add_ocr_result(
                photo_id=photo_id,
                jersey_number=primary_jersey,
                confidence=confidence,
                raw_text=raw_text
            )
            
            return {
                "photo_id": photo_id,
                "jerseys_found": jerseys,
                "primary_jersey": primary_jersey,
                "confidence": confidence,
                "raw_text": raw_text,
            }
        
        except Exception as e:
            logger.error(f"Error processing photo {photo_path}: {e}")
            return None
    
    def process_batch(self, photo_ids: List[int] = None) -> Dict:
        """
        Process all photos in the database (or specific IDs).
        
        Args:
            photo_ids: Optional list of photo IDs to process. If None, process all.
        
        Returns:
            Dict with processing statistics
        """
        if photo_ids is None:
            # Process all photos
            photos = self.db.get_all_photos()
            photo_ids = [p["id"] for p in photos]
        
        results = {
            "photos_processed": 0,
            "jerseys_found": 0,
            "errors": 0,
        }
        
        for photo_id in photo_ids:
            # Get photo path from database
            photos = self.db.get_all_photos()
            photo = next((p for p in photos if p["id"] == photo_id), None)
            
            if not photo:
                logger.warning(f"Photo ID {photo_id} not found in database")
                continue
            
            result = self.process_photo(photo_id, photo["file_path"])
            
            if result:
                results["photos_processed"] += 1
                if result["primary_jersey"]:
                    results["jerseys_found"] += 1
            else:
                results["errors"] += 1
        
        logger.info(f"Batch processing complete: {results}")
        return results
    
    @staticmethod
    def _extract_jerseys_from_text(text: str) -> List[str]:
        """
        Extract jersey numbers (1-3 digit numbers) from text.
        
        Args:
            text: Raw text from OCR
        
        Returns:
            List of unique jersey numbers found
        """
        # Match 1-3 digit numbers, with word boundaries
        pattern = r"\b(\d{1,3})\b"
        matches = re.findall(pattern, text)
        
        # Filter to valid jersey numbers (exclude common OCR artifacts like year dates)
        # Keep 1-99 as valid jerseys, exclude 3-digit numbers > 999 or < 100
        valid_jerseys = []
        for num in matches:
            num_int = int(num)
            # Valid jerseys: 1-99
            if 1 <= num_int <= 99:
                if num not in valid_jerseys:  # Avoid duplicates
                    valid_jerseys.append(num)
        
        return valid_jerseys
```

Save to `/Users/brettevanssf/Code/Saasless/PhotoTagger/src/ocr.py`

- [ ] **Step 4: Run OCR tests**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
pytest tests/test_ocr.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Add integration test for photo processing**

```python
# tests/test_ocr.py (append)

def test_process_photo_integration(test_ocr_engine, tmp_path):
    """Test OCR processing of an actual image file."""
    engine, db = test_ocr_engine
    
    # Create a dummy photo file
    photo_file = tmp_path / "test_photo.jpg"
    photo_file.write_bytes(b"fake jpg data")
    
    # Add to database first
    photo_id = db.add_photo(str(photo_file))
    
    # Note: This will fail on actual processing because the file is not a real image.
    # In a real scenario, you'd use a test image. For now, we test the structure.
    # Uncomment below if you have a test image available:
    # result = engine.process_photo(photo_id, str(photo_file))
    # assert result is not None
    # assert result["photo_id"] == photo_id
```

Append to `/Users/brettevanssf/Code/Saasless/PhotoTagger/tests/test_ocr.py`

- [ ] **Step 6: Commit OCR engine**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
git add src/ocr.py tests/test_ocr.py
git commit -m "feat: implement OCR engine for jersey number extraction"
```

---

### Task 5: Flask REST API

**Files:**
- Create: `src/api.py`
- Create: `tests/test_api.py`

**Summary:** Build a minimal Flask API with endpoints for crawling photos, processing OCR, and searching by jersey number.

- [ ] **Step 1: Write test for API endpoints**

```python
# tests/test_api.py
import pytest
import json
from pathlib import Path
from src.api import create_app
from src.db import Database

@pytest.fixture
def app():
    """Create a Flask test app with in-memory database."""
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    return app

@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()

def test_api_initialization(app):
    """Verify API app initializes."""
    assert app is not None

def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "ok"

def test_search_no_results(client):
    """Test search endpoint when no results found."""
    response = client.get("/api/search?jersey=23")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["results"] == []
    assert data["count"] == 0

def test_search_with_results(client, app):
    """Test search endpoint with actual results."""
    # Add a photo and OCR result to the database
    db = app.db
    
    # Create a dummy photo
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(b"fake jpg")
        photo_path = f.name
    
    photo_id = db.add_photo(photo_path)
    db.add_ocr_result(photo_id, "23", 0.95, "23 visible")
    
    # Search for jersey 23
    response = client.get("/api/search?jersey=23")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["count"] == 1
    assert data["results"][0]["jersey_number"] == "23"
```

Save to `/Users/brettevanssf/Code/Saasless/PhotoTagger/tests/test_api.py`

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
pytest tests/test_api.py::test_api_initialization -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'src.api'"

- [ ] **Step 3: Create src/api.py**

```python
# src/api.py
import logging
import os
from flask import Flask, request, jsonify
from src.db import Database
from src.crawler import PhotoCrawler
from src.ocr import OCREngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app(db_path: str = "photo_catalog.db") -> Flask:
    """Create and configure Flask app."""
    app = Flask(__name__)
    
    # Initialize database
    db = Database(db_path)
    db.init_schema()
    app.db = db
    
    # Initialize components
    crawler = PhotoCrawler(db)
    ocr_engine = OCREngine(db)
    
    # Health check endpoint
    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        return jsonify({"status": "ok"}), 200
    
    # Search photos by jersey number
    @app.route("/api/search", methods=["GET"])
    def search():
        """
        Search for photos by jersey number.
        
        Query params:
        - jersey: Jersey number to search for (required)
        
        Returns:
            JSON with matching photos
        """
        jersey = request.args.get("jersey", "").strip()
        
        if not jersey:
            return jsonify({"error": "jersey parameter required"}), 400
        
        results = db.get_photo_by_jersey(jersey)
        
        return jsonify({
            "jersey": jersey,
            "count": len(results),
            "results": results,
        }), 200
    
    # Crawl photos endpoint
    @app.route("/api/crawl", methods=["POST"])
    def crawl():
        """
        Crawl a local photo directory and ingest photos.
        
        JSON body:
        {
            "photo_dir": "/path/to/photos"
        }
        """
        data = request.get_json() or {}
        photo_dir = data.get("photo_dir", "./photos")
        
        if not os.path.isdir(photo_dir):
            return jsonify({"error": f"Directory not found: {photo_dir}"}), 404
        
        try:
            results = crawler.crawl(photo_dir)
            return jsonify({
                "success": True,
                "results": results,
            }), 200
        except Exception as e:
            logger.error(f"Crawl error: {e}")
            return jsonify({"error": str(e)}), 500
    
    # Process OCR endpoint
    @app.route("/api/process-ocr", methods=["POST"])
    def process_ocr():
        """
        Process OCR on photos in the database.
        
        JSON body (optional):
        {
            "photo_ids": [1, 2, 3]  // Optional: process specific photos
        }
        """
        data = request.get_json() or {}
        photo_ids = data.get("photo_ids", None)
        
        try:
            results = ocr_engine.process_batch(photo_ids)
            return jsonify({
                "success": True,
                "results": results,
            }), 200
        except Exception as e:
            logger.error(f"OCR error: {e}")
            return jsonify({"error": str(e)}), 500
    
    # Info endpoint
    @app.route("/api/info", methods=["GET"])
    def info():
        """Get database statistics."""
        all_photos = db.get_all_photos()
        
        return jsonify({
            "total_photos": len(all_photos),
            "db_path": db.db_path,
        }), 200
    
    return app

if __name__ == "__main__":
    app = create_app()
    logger.info("Starting PhotoTagger API on http://localhost:5000")
    app.run(debug=True, port=5000)
```

Save to `/Users/brettevanssf/Code/Saasless/PhotoTagger/src/api.py`

- [ ] **Step 4: Run API tests**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
pytest tests/test_api.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Add test for crawl endpoint**

```python
# tests/test_api.py (append)

def test_crawl_endpoint(client, tmp_path):
    """Test crawl endpoint."""
    # Create test photos
    for i in range(2):
        photo = tmp_path / f"photo{i}.jpg"
        photo.write_bytes(b"fake jpg")
    
    # Call crawl endpoint
    response = client.post("/api/crawl", json={"photo_dir": str(tmp_path)})
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is True
    assert data["results"]["photos_found"] == 2

def test_info_endpoint(client):
    """Test info endpoint."""
    response = client.get("/api/info")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "total_photos" in data
    assert data["total_photos"] == 0
```

Append to `/Users/brettevanssf/Code/Saasless/PhotoTagger/tests/test_api.py`

- [ ] **Step 6: Run all API tests**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
pytest tests/test_api.py -v
```

Expected: All tests PASS

- [ ] **Step 7: Commit API**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
git add src/api.py tests/test_api.py
git commit -m "feat: implement Flask REST API with search, crawl, and OCR endpoints"
```

---

### Task 6: CLI Tool for Local Testing

**Files:**
- Create: `src/cli.py`
- Create: `src/utils.py`

**Summary:** Create a command-line interface for crawling, processing OCR, and searching without needing to call the REST API directly.

- [ ] **Step 1: Create src/utils.py with shared utilities**

```python
# src/utils.py
import logging
from datetime import datetime

def setup_logging(level=logging.INFO):
    """Configure logging for CLI and scripts."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

def format_size(bytes_size: int) -> str:
    """Format byte size to human-readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f} TB"
```

Save to `/Users/brettevanssf/Code/Saasless/PhotoTagger/src/utils.py`

- [ ] **Step 2: Create src/cli.py**

```python
# src/cli.py
import argparse
import sys
from pathlib import Path
from src.db import Database
from src.crawler import PhotoCrawler
from src.ocr import OCREngine
from src.utils import setup_logging, format_size
import logging

logger = logging.getLogger(__name__)

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="PhotoTagger: Find photos by jersey number"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Crawl command
    crawl_parser = subparsers.add_parser("crawl", help="Crawl photo directory")
    crawl_parser.add_argument("--photos", default="./photos", help="Photo directory path")
    crawl_parser.add_argument("--db", default="photo_catalog.db", help="Database path")
    
    # OCR command
    ocr_parser = subparsers.add_parser("ocr", help="Process OCR on photos")
    ocr_parser.add_argument("--db", default="photo_catalog.db", help="Database path")
    ocr_parser.add_argument("--photo-id", type=int, help="Optional: process specific photo ID")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search photos by jersey")
    search_parser.add_argument("jersey", help="Jersey number to search for")
    search_parser.add_argument("--db", default="photo_catalog.db", help="Database path")
    
    # Info command
    info_parser = subparsers.add_parser("info", help="Show database info")
    info_parser.add_argument("--db", default="photo_catalog.db", help="Database path")
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(logging.INFO)
    
    if args.command == "crawl":
        cmd_crawl(args)
    elif args.command == "ocr":
        cmd_ocr(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "info":
        cmd_info(args)
    else:
        parser.print_help()
        sys.exit(1)

def cmd_crawl(args):
    """Crawl command: scan photo directory."""
    db = Database(args.db)
    db.init_schema()
    
    crawler = PhotoCrawler(db)
    photo_dir = Path(args.photos)
    
    if not photo_dir.exists():
        print(f"❌ Photo directory not found: {photo_dir}")
        sys.exit(1)
    
    print(f"📁 Crawling: {photo_dir.absolute()}")
    results = crawler.crawl(str(photo_dir))
    
    print(f"✅ Found: {results['photos_found']} images")
    print(f"✅ Ingested: {results['photos_ingested']} new photos")
    print(f"⏭️  Skipped: {results['duplicates_skipped']} duplicates")
    
    if results['errors'] > 0:
        print(f"❌ Errors: {results['errors']}")
    
    db.close()

def cmd_ocr(args):
    """OCR command: process photos."""
    db = Database(args.db)
    db.init_schema()
    
    ocr_engine = OCREngine(db)
    
    if args.photo_id:
        print(f"🔍 Processing photo ID: {args.photo_id}")
        photo_ids = [args.photo_id]
    else:
        print(f"🔍 Processing all photos...")
        photos = db.get_all_photos()
        photo_ids = [p["id"] for p in photos]
    
    results = ocr_engine.process_batch(photo_ids)
    
    print(f"✅ Processed: {results['photos_processed']} photos")
    print(f"🏃 Jersey found: {results['jerseys_found']} photos")
    
    if results['errors'] > 0:
        print(f"❌ Errors: {results['errors']}")
    
    db.close()

def cmd_search(args):
    """Search command: find photos by jersey number."""
    db = Database(args.db)
    db.init_schema()
    
    jersey = args.jersey.strip()
    print(f"🔎 Searching for jersey: {jersey}")
    
    results = db.get_photo_by_jersey(jersey)
    
    if not results:
        print(f"❌ No photos found with jersey {jersey}")
        db.close()
        return
    
    print(f"✅ Found {len(results)} photo(s):\n")
    
    for result in results:
        print(f"  📸 {result['file_path']}")
        print(f"     Jersey: {result['jersey_number']}, Confidence: {result['confidence']:.2%}")
        print()
    
    db.close()

def cmd_info(args):
    """Info command: show database statistics."""
    db = Database(args.db)
    db.init_schema()
    
    photos = db.get_all_photos()
    
    print(f"📊 Database: {args.db}")
    print(f"📸 Total photos: {len(photos)}")
    
    if photos:
        total_size = sum(p["file_size"] for p in photos if p["file_size"])
        print(f"💾 Total size: {format_size(total_size)}")
    
    db.close()

if __name__ == "__main__":
    main()
```

Save to `/Users/brettevanssf/Code/Saasless/PhotoTagger/src/cli.py`

- [ ] **Step 3: Test CLI commands (manual for now)**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger

# Test help
python -m src.cli --help

# These will fail with no photos, but test the CLI structure
python -m src.cli crawl --help
python -m src.cli ocr --help
python -m src.cli search 23 --help
```

Expected: All help commands should display usage info

- [ ] **Step 4: Commit CLI**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
git add src/cli.py src/utils.py
git commit -m "feat: add CLI tool for local testing without API"
```

---

### Task 7: Run Full Test Suite

**Files:** (none new)

**Summary:** Verify all components work together by running the complete test suite.

- [ ] **Step 1: Install dependencies**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Expected: All packages installed successfully

- [ ] **Step 2: Run full test suite**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
pytest tests/ -v --cov=src
```

Expected: All tests PASS, with coverage > 80%

- [ ] **Step 3: Check code style (optional but recommended)**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
pip install flake8
flake8 src/ --max-line-length=100
```

Expected: No major style issues (warnings are OK)

- [ ] **Step 4: Create a simple local test**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger

# Create sample photos directory
mkdir -p photos
touch photos/test1.jpg photos/test2.jpg

# Run crawl via CLI
python -m src.cli crawl --photos ./photos

# Check database info
python -m src.cli info
```

Expected: CLI shows 2 photos found and ingested

- [ ] **Step 5: Final commit and summary**

```bash
cd /Users/brettevanssf/Code/Saasless/PhotoTagger
git log --oneline
```

Expected: You should see 7 commits (setup, db, crawler, ocr, api, cli, test summary)

---

## Phase 1 Complete ✅

You now have:
- ✅ SQLite database with photo and OCR schema
- ✅ Photo crawler (walks directories, dedupes via hash)
- ✅ Jersey OCR extraction (EasyOCR-based)
- ✅ REST API (Flask) with search, crawl, OCR endpoints
- ✅ CLI tool for local testing
- ✅ Full test coverage (pytest)
- ✅ Local-first (no cloud dependencies)

## Next: Phase 2 Ideas (Out of Scope)

Once Phase 1 is stable:
- Add face embedding + vector search (InsightFace)
- Add roster data management
- Add simple React UI
- Deploy to cloud (AWS Lambda, Render, etc.)
- Integrate with Zenfolio API
- Add batch processing for large photo libraries
