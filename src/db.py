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

        # Faces table: store detected faces and embeddings (Phase 2A)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS faces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                photo_id INTEGER NOT NULL,
                embedding BLOB NOT NULL,
                bbox_x0 INTEGER,
                bbox_y0 INTEGER,
                bbox_x1 INTEGER,
                bbox_y1 INTEGER,
                confidence REAL,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (photo_id) REFERENCES photos(id) ON DELETE CASCADE
            )
        """)

        # Rosters table: player name mapping (Phase 2A)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rosters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_name TEXT NOT NULL,
                team_year INTEGER NOT NULL,
                jersey_number TEXT NOT NULL,
                player_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(team_name, team_year, jersey_number)
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

    def add_face(self, photo_id: int, embedding: List[float], bbox: List[int], confidence: float) -> int:
        """
        Add a detected face to the database.

        Args:
            photo_id: ID of the photo
            embedding: 384-dim face embedding vector
            bbox: [x0, y0, x1, y1] bounding box
            confidence: Face detection confidence (0-1)

        Returns:
            Face ID
        """
        import json
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO faces (photo_id, embedding, bbox_x0, bbox_y0, bbox_x1, bbox_y1, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (photo_id, json.dumps(embedding), bbox[0], bbox[1], bbox[2], bbox[3], confidence))
        self.conn.commit()
        return cursor.lastrowid

    def get_faces_by_photo(self, photo_id: int) -> List[Dict]:
        """Get all faces detected in a photo."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, photo_id, embedding, bbox_x0, bbox_y0, bbox_x1, bbox_y1, confidence
            FROM faces
            WHERE photo_id = ?
            ORDER BY confidence DESC
        """, (photo_id,))

        results = []
        for row in cursor.fetchall():
            import json
            results.append({
                "id": row[0],
                "photo_id": row[1],
                "embedding": json.loads(row[2]),
                "bbox": [row[3], row[4], row[5], row[6]],
                "confidence": row[7]
            })
        return results

    def add_roster_entry(self, team_name: str, team_year: int, jersey_number: str, player_name: str):
        """Add a player to the roster."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO rosters (team_name, team_year, jersey_number, player_name)
            VALUES (?, ?, ?, ?)
        """, (team_name, team_year, jersey_number, player_name))
        self.conn.commit()

    def get_player_name(self, team_name: str, team_year: int, jersey_number: str) -> Optional[str]:
        """Look up player name by jersey."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT player_name FROM rosters
            WHERE team_name = ? AND team_year = ? AND jersey_number = ?
        """, (team_name, team_year, jersey_number))
        result = cursor.fetchone()
        return result[0] if result else None

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
