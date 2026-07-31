import sqlite3
import hashlib
import threading
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from src.schema import init_schema
from src.repositories.job import JobRepository
from src.repositories.game_context import GameContextRepository
from src.repositories.batch import BatchRepository
from src.repositories.face import FaceRepository
from src.repositories.cluster import ClusterRepository
from src.repositories.roster import RosterRepository
from src.repositories.photo import PhotoRepository
from src.review_service import ReviewService

class Database:
    def __init__(self, db_path: str = "photo_catalog.db"):
        """Initialize database connection."""
        self.db_path = db_path
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Return rows as dicts

        # Repository instances — all share the same conn + lock
        self.jobs = JobRepository(self.conn, self._lock)
        self.context = GameContextRepository(self.conn, self._lock)
        self.batches = BatchRepository(self.conn, self._lock)
        self.faces = FaceRepository(self.conn, self._lock)
        self.clusters = ClusterRepository(self.conn, self._lock)
        self.roster = RosterRepository(self.conn, self._lock)
        self.photos = PhotoRepository(self.conn, self._lock)

        # ReviewService composes photo, roster, and context repos for cross-domain queries
        self.review = ReviewService(self.photos, self.roster, self.context)

    def init_schema(self):
        """Create database tables if they don't exist."""
        init_schema(self.conn)

    # Legacy delegation stubs for backward compatibility with tests
    def get_all_faces(self) -> List[Dict]:
        """Delegation stub: get all faces via FaceRepository."""
        return self.faces.get_all_faces()

    def add_ocr_result(self, photo_id: int, jersey_number: Optional[str], confidence: float, raw_text: str, uniform_color: Optional[str] = None):
        """Delegation stub: add OCR result via PhotoRepository."""
        return self.photos.add_ocr_result(photo_id, jersey_number, confidence, raw_text, uniform_color)

    def get_processing_summary(self) -> Dict:
        """Delegation stub: get processing summary via ReviewService."""
        return self.review.get_processing_summary()

    def get_confirmed_photos(self, limit: int = 60, offset: int = 0) -> List[Dict]:
        """Delegation stub: get confirmed photos via ReviewService."""
        return self.review.get_confirmed_photos(limit, offset)

    def get_review_photos(self, limit: int = 60, offset: int = 0) -> List[Dict]:
        """Delegation stub: get photos needing review via ReviewService."""
        return self.review.get_review_photos(limit, offset)

    def get_photos_by_face_ids(self, cluster_id: int, face_ids: List[int]) -> List[Dict]:
        """Return photo paths for selected faces that currently belong to a cluster."""
        if not face_ids:
            return []
        with self._lock:
            cursor = self.conn.cursor()
            placeholders = ",".join("?" for _ in face_ids)
            cursor.execute(f"""
                SELECT f.id as face_id, p.id as photo_id, p.file_path
                FROM faces f
                JOIN photos p ON p.id = f.photo_id
                WHERE f.cluster_id = ?
                  AND f.id IN ({placeholders})
                ORDER BY f.id
            """, [cluster_id, *face_ids])
            return [
                {"face_id": row[0], "photo_id": row[1], "file_path": row[2]}
                for row in cursor.fetchall()
            ]

    def get_player_names_and_paths_for_faces(self, face_ids: List[int]) -> List[Dict]:
        """Resolve each face's current player_name (via cluster) and photo file_path.

        Call this BEFORE deassigning — the cluster link (and thus the player
        name) is gone once faces.cluster_id is cleared.
        """
        if not face_ids:
            return []
        with self._lock:
            cursor = self.conn.cursor()
            placeholders = ",".join("?" for _ in face_ids)
            cursor.execute(f"""
                SELECT f.id as face_id, p.file_path, pc.player_name
                FROM faces f
                JOIN photos p ON p.id = f.photo_id
                LEFT JOIN player_clusters pc ON f.cluster_id = pc.id
                WHERE f.id IN ({placeholders})
            """, face_ids)
            return [
                {"face_id": row[0], "file_path": row[1], "player_name": row[2]}
                for row in cursor.fetchall()
            ]

    def reset_all_data(self) -> Dict:
        """Delete every row from all user-data tables.

        Clears photos, OCR results, faces, player clusters, rosters,
        photo batches, game context, and processing jobs.
        Returns counts of rows deleted per table.
        """
        tables = [
            "ocr_results",
            "faces",
            "player_clusters",
            "photo_batches",
            "photos",
            "rosters",
            "game_context_teams",
            "processing_jobs",
        ]
        deleted: Dict[str, int] = {}
        with self._lock:
            cursor = self.conn.cursor()
            for table in tables:
                cursor.execute(f"DELETE FROM {table}")
                deleted[table] = cursor.rowcount
            self.conn.commit()
        return deleted

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
