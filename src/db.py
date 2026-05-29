import sqlite3
import hashlib
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

class Database:
    def __init__(self, db_path: str = "photo_catalog.db"):
        """Initialize database connection."""
        self.db_path = db_path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
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

        # Player clusters table: grouped face identities
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS player_clusters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                face_count INTEGER DEFAULT 0,
                photo_count INTEGER DEFAULT 0,
                thumbnail_face_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Add cluster_id column to faces if it doesn't exist yet
        try:
            cursor.execute("ALTER TABLE faces ADD COLUMN cluster_id INTEGER REFERENCES player_clusters(id)")
        except Exception:
            pass  # Column already exists

        # Add player_name / jersey_number to player_clusters if not present
        try:
            cursor.execute("ALTER TABLE player_clusters ADD COLUMN player_name TEXT")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE player_clusters ADD COLUMN jersey_number TEXT")
        except Exception:
            pass

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
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM photos")
            return [dict(row) for row in cursor.fetchall()]

    def get_photo_by_id(self, photo_id: int) -> Optional[Dict]:
        """Get a single photo by its ID."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM photos WHERE id = ?", (photo_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

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

    def get_all_faces(self) -> List[Dict]:
        """Get all faces with their embeddings (for clustering)."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, photo_id, embedding, bbox_x0, bbox_y0, bbox_x1, bbox_y1, confidence, cluster_id
                FROM faces
                ORDER BY id
            """)
            results = []
            for row in cursor.fetchall():
                import json
                results.append({
                    "id": row[0],
                    "photo_id": row[1],
                    "embedding": json.loads(row[2]),
                    "bbox": [row[3], row[4], row[5], row[6]],
                    "confidence": row[7],
                    "cluster_id": row[8],
                })
            return results

    def get_face_by_id(self, face_id: int) -> Optional[Dict]:
        """Get a single face by its ID."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, photo_id, embedding, bbox_x0, bbox_y0, bbox_x1, bbox_y1, confidence, cluster_id
                FROM faces WHERE id = ?
            """, (face_id,))
            row = cursor.fetchone()
            if not row:
                return None
            import json
            return {
                "id": row[0],
                "photo_id": row[1],
                "embedding": json.loads(row[2]),
                "bbox": [row[3], row[4], row[5], row[6]],
                "confidence": row[7],
                "cluster_id": row[8],
            }

    def clear_clusters(self):
        """Remove all cluster assignments (reset before re-clustering)."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("UPDATE faces SET cluster_id = NULL")
            cursor.execute("DELETE FROM player_clusters")
            self.conn.commit()

    def add_player_cluster(self, face_count: int, photo_count: int, thumbnail_face_id: Optional[int]) -> int:
        """Insert a player cluster and return its ID."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO player_clusters (face_count, photo_count, thumbnail_face_id)
                VALUES (?, ?, ?)
            """, (face_count, photo_count, thumbnail_face_id))
            self.conn.commit()
            return cursor.lastrowid

    def assign_face_to_cluster(self, face_id: int, cluster_id: int):
        """Set the cluster_id on a face row."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("UPDATE faces SET cluster_id = ? WHERE id = ?", (cluster_id, face_id))
            self.conn.commit()

    def get_all_player_clusters(self) -> List[Dict]:
        """Get all player clusters with stats."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, face_count, photo_count, thumbnail_face_id, created_at,
                       player_name, jersey_number
                FROM player_clusters
                ORDER BY photo_count DESC
            """)
            return [
                {
                    "id": row[0],
                    "face_count": row[1],
                    "photo_count": row[2],
                    "thumbnail_face_id": row[3],
                    "created_at": row[4],
                    "player_name": row[5],
                    "jersey_number": row[6],
                }
                for row in cursor.fetchall()
            ]

    def get_photos_by_cluster(self, cluster_id: int) -> List[Dict]:
        """Get all photos that contain a face in this cluster."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT DISTINCT p.id, p.file_path, p.ingested_at,
                       f.id as face_id, f.bbox_x0, f.bbox_y0, f.bbox_x1, f.bbox_y1, f.confidence
                FROM photos p
                JOIN faces f ON f.photo_id = p.id
                WHERE f.cluster_id = ?
                ORDER BY p.id
            """, (cluster_id,))
            return [
                {
                    "id": row[0],
                    "file_path": row[1],
                    "added_at": row[2],
                    "face_id": row[3],
                    "face_bbox": [row[4], row[5], row[6], row[7]],
                    "face_confidence": row[8],
                }
                for row in cursor.fetchall()
            ]

    def get_face_count(self) -> int:
        """Return total number of detected faces."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM faces")
            return cursor.fetchone()[0]

    # ── Roster CRUD ─────────────────────────────────────────────────────────────

    def get_all_roster_entries(self) -> List[Dict]:
        """Return every roster row ordered by team then jersey number."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, team_name, team_year, jersey_number, player_name
                FROM rosters
                ORDER BY team_name, CAST(jersey_number AS INTEGER)
            """)
            return [
                {"id": r[0], "team_name": r[1], "team_year": r[2],
                 "jersey_number": r[3], "player_name": r[4]}
                for r in cursor.fetchall()
            ]

    def delete_roster_entry(self, entry_id: int):
        """Delete a single roster row by primary key."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM rosters WHERE id = ?", (entry_id,))
            self.conn.commit()

    def search_roster(self, query: str) -> List[Dict]:
        """Fuzzy search roster by player name or jersey number (max 10 results)."""
        with self._lock:
            cursor = self.conn.cursor()
            pattern = f"%{query}%"
            cursor.execute("""
                SELECT id, team_name, jersey_number, player_name
                FROM rosters
                WHERE player_name LIKE ? OR jersey_number LIKE ?
                ORDER BY CAST(jersey_number AS INTEGER)
                LIMIT 10
            """, (pattern, pattern))
            return [
                {"id": r[0], "team_name": r[1], "jersey_number": r[2], "player_name": r[3]}
                for r in cursor.fetchall()
            ]

    # ── Processing summary ───────────────────────────────────────────────────────

    def get_processing_summary(self) -> Dict:
        """Return counts: total photos, auto-tagged (jersey→roster match), needs review."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM photos")
            total = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COUNT(DISTINCT o.photo_id)
                FROM ocr_results o
                INNER JOIN rosters r ON r.jersey_number = o.jersey_number
                WHERE o.jersey_number IS NOT NULL
            """)
            tagged = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COUNT(DISTINCT o.photo_id)
                FROM ocr_results o
                LEFT JOIN rosters r ON r.jersey_number = o.jersey_number
                WHERE o.jersey_number IS NOT NULL AND r.id IS NULL
            """)
            needs_review = cursor.fetchone()[0]

            return {"total_photos": total, "tagged": tagged, "needs_review": needs_review}

    def get_confirmed_photos(self, limit: int = 60, offset: int = 0) -> List[Dict]:
        """Photos where OCR jersey matched a roster player."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT DISTINCT p.id, p.file_path, o.jersey_number, r.player_name, o.confidence
                FROM photos p
                JOIN ocr_results o ON o.photo_id = p.id
                JOIN rosters r ON r.jersey_number = o.jersey_number
                WHERE o.jersey_number IS NOT NULL
                ORDER BY o.confidence DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            return [
                {"id": r[0], "file_path": r[1], "jersey_number": r[2],
                 "player_name": r[3], "confidence": r[4]}
                for r in cursor.fetchall()
            ]

    def get_review_photos(self, limit: int = 60, offset: int = 0) -> List[Dict]:
        """Photos where OCR found a jersey but it didn't match any roster entry."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT DISTINCT p.id, p.file_path, o.jersey_number, o.confidence
                FROM photos p
                JOIN ocr_results o ON o.photo_id = p.id
                LEFT JOIN rosters r ON r.jersey_number = o.jersey_number
                WHERE o.jersey_number IS NOT NULL AND r.id IS NULL
                ORDER BY o.confidence DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            return [
                {"id": r[0], "file_path": r[1], "jersey_number": r[2], "confidence": r[3]}
                for r in cursor.fetchall()
            ]

    def deassign_faces(self, face_ids: List[int]):
        """Remove specific faces from their cluster (set cluster_id = NULL)."""
        if not face_ids:
            return
        with self._lock:
            cursor = self.conn.cursor()
            placeholders = ','.join('?' * len(face_ids))
            cursor.execute(f"UPDATE faces SET cluster_id = NULL WHERE id IN ({placeholders})", face_ids)
            self.conn.commit()

    def assign_cluster_to_player(self, cluster_id: int, player_name: str, jersey_number: str):
        """Attach a player name and jersey to a face cluster."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE player_clusters SET player_name = ?, jersey_number = ?
                WHERE id = ?
            """, (player_name, jersey_number, cluster_id))
            self.conn.commit()

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
