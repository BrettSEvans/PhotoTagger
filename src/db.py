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
