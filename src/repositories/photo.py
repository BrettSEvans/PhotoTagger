"""PhotoRepository - handles photo records and OCR results."""

import hashlib
from pathlib import Path
from typing import Optional, List, Dict

from src.repositories._base import BaseRepository


class PhotoRepository(BaseRepository):
    """Repository for photos and ocr_results tables."""

    def add_photo(self, file_path: str, file_hash: Optional[str] = None, source_folder: Optional[str] = None, batch_id: Optional[int] = None) -> int:
        """Add a photo to the database. Returns the photo ID."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Photo not found: {file_path}")

        # Generate file hash if not provided
        if file_hash is None:
            file_hash = self._compute_file_hash(file_path)

        file_size = path.stat().st_size

        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO photos (file_path, file_hash, file_size, source_folder, batch_id)
                VALUES (?, ?, ?, ?, ?)
            """, (str(file_path), file_hash, file_size, source_folder, batch_id))
            self._conn.commit()

            return cursor.lastrowid

    def add_ocr_result(
        self,
        photo_id: int,
        jersey_number: Optional[str],
        confidence: float,
        raw_text: str,
        uniform_color: Optional[str] = None,
        bbox: Optional[List[int]] = None,
        roster_entry_id: Optional[int] = None,
    ):
        """Add OCR extraction results for a photo.

        Args:
            photo_id: Photo ID in database
            jersey_number: Extracted jersey number (e.g. "31")
            confidence: OCR confidence (0-1)
            raw_text: Raw OCR text
            uniform_color: Uniform color from game context
            bbox: Bounding box [x0, y0, x1, y1] or None
            roster_entry_id: ID of matched roster entry, or None
        """
        with self._lock:
            cursor = self._conn.cursor()
            bbox_x0, bbox_y0, bbox_x1, bbox_y1 = (None, None, None, None)
            if bbox and len(bbox) >= 4:
                bbox_x0, bbox_y0, bbox_x1, bbox_y1 = bbox[0], bbox[1], bbox[2], bbox[3]

            cursor.execute("""
                INSERT INTO ocr_results (
                    photo_id, jersey_number, uniform_color, confidence, raw_text,
                    bbox_x0, bbox_y0, bbox_x1, bbox_y1, roster_entry_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (photo_id, jersey_number, uniform_color, confidence, raw_text,
                  bbox_x0, bbox_y0, bbox_x1, bbox_y1, roster_entry_id))
            self._conn.commit()

    def get_photo_by_jersey(self, jersey_number: str) -> List[Dict]:
        """Find all photos matching a jersey number."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT p.id, p.file_path, o.jersey_number, o.confidence, o.raw_text
                FROM photos p
                JOIN ocr_results o ON p.id = o.photo_id
                WHERE o.jersey_number = ?
                ORDER BY o.confidence DESC
            """, (jersey_number,))

            return [dict(row) for row in cursor.fetchall()]

    def count_photos(self) -> int:
        """Return the total number of photos in the database (fast COUNT query)."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM photos")
            return cursor.fetchone()[0]

    def get_all_photos(self, limit: Optional[int] = None, offset: int = 0) -> List[Dict]:
        """Get photos in the database.

        When *limit* is ``None`` (default) all rows are returned — suitable for
        internal use (detection, clustering).  The HTTP endpoint should always
        supply *limit* and *offset* so that the SQL engine handles pagination
        rather than loading every row into Python memory.
        """
        with self._lock:
            cursor = self._conn.cursor()
            if limit is not None:
                cursor.execute(
                    "SELECT * FROM photos ORDER BY id LIMIT ? OFFSET ?",
                    (limit, offset),
                )
            else:
                cursor.execute("SELECT * FROM photos ORDER BY id")
            return [dict(row) for row in cursor.fetchall()]

    def get_photo_by_id(self, photo_id: int) -> Optional[Dict]:
        """Get a single photo by its ID."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT * FROM photos WHERE id = ?", (photo_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_photo_ocr(self, photo_id: int) -> Optional[Dict]:
        """Get OCR results for a specific photo."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT * FROM ocr_results WHERE photo_id = ? ORDER BY processed_at DESC LIMIT 1
            """, (photo_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_latest_ocr_by_photo_ids(self, photo_ids: List[int]) -> Dict[int, Dict]:
        """Return the latest OCR row for each given photo id, keyed by photo_id.

        Single query instead of one lookup per photo (avoids N+1 in clustering auto-match).
        """
        if not photo_ids:
            return {}
        with self._lock:
            cursor = self._conn.cursor()
            placeholders = ",".join("?" for _ in photo_ids)
            cursor.execute(f"""
                SELECT o.*
                FROM ocr_results o
                WHERE o.photo_id IN ({placeholders})
                  AND o.id = (
                      SELECT MAX(o2.id)
                      FROM ocr_results o2
                      WHERE o2.photo_id = o.photo_id
                  )
            """, list(photo_ids))
            return {row["photo_id"]: dict(row) for row in cursor.fetchall()}

    def photo_exists(self, file_hash: str) -> bool:
        """Check if a photo with this hash already exists."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT id FROM photos WHERE file_hash = ?", (file_hash,))
            return cursor.fetchone() is not None

    def get_assigned_player_for_photo(self, photo_id: int) -> Optional[str]:
        """Get the player name assigned to a photo via cluster assignment.

        Returns the player_name if the photo contains a face in an assigned cluster,
        else None.
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT DISTINCT pc.player_name
                FROM faces f
                JOIN player_clusters pc ON f.cluster_id = pc.id
                WHERE f.photo_id = ? AND pc.player_name IS NOT NULL
                LIMIT 1
            """, (photo_id,))
            result = cursor.fetchone()
            return result[0] if result else None

    def get_ocr_by_photo(self, photo_id: int) -> List[Dict]:
        """Get all OCR results for a photo with roster information.

        Returns OCR results with linked roster information if available.

        Args:
            photo_id: Photo ID in database

        Returns:
            List of dicts with OCR result and roster info:
            {
                "id": ocr_result_id,
                "photo_id": photo_id,
                "jersey_number": "31",
                "confidence": 0.94,
                "bbox": [x0, y0, x1, y1],
                "roster_entry_id": 42,
                "player_name": "Nathan De Morgan",
                "team_name": "Carleton (CUT)",
                "uniform_color": "red",
            }
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT
                    o.id,
                    o.photo_id,
                    o.jersey_number,
                    o.confidence,
                    o.bbox_x0, o.bbox_y0, o.bbox_x1, o.bbox_y1,
                    o.roster_entry_id,
                    r.player_name,
                    r.team_name,
                    r.uniform_color
                FROM ocr_results o
                LEFT JOIN rosters r ON o.roster_entry_id = r.id
                WHERE o.photo_id = ?
                ORDER BY o.processed_at DESC
            """, (photo_id,))

            results = []
            for row in cursor.fetchall():
                bbox = [row[4], row[5], row[6], row[7]] if all(x is not None for x in row[4:8]) else None
                results.append({
                    "id": row[0],
                    "photo_id": row[1],
                    "jersey_number": row[2],
                    "confidence": row[3],
                    "bbox": bbox,
                    "roster_entry_id": row[8],
                    "player_name": row[9],
                    "team_name": row[10],
                    "uniform_color": row[11],
                })
            return results

    def get_jersey_detections(self, photo_id: int) -> List[Dict]:
        """Get all jersey number detections for a photo with roster information.

        Returns jersey detections with linked roster information (player name, team, etc).

        Args:
            photo_id: Photo ID in database

        Returns:
            List of dicts with jersey detection and roster info:
            {
                "id": ocr_result_id,
                "jersey_number": "31",
                "confidence": 0.94,
                "bbox": [x0, y0, x1, y1],
                "roster_entry_id": 42,
                "player_name": "Nathan De Morgan",
                "team_name": "Carleton (CUT)",
                "uniform_color": "red",
            }
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT
                    o.id,
                    o.jersey_number,
                    o.confidence,
                    o.bbox_x0, o.bbox_y0, o.bbox_x1, o.bbox_y1,
                    o.roster_entry_id,
                    r.player_name,
                    r.team_name,
                    r.uniform_color
                FROM ocr_results o
                LEFT JOIN rosters r ON o.roster_entry_id = r.id
                WHERE o.photo_id = ?
                ORDER BY o.processed_at DESC
            """, (photo_id,))

            results = []
            for row in cursor.fetchall():
                bbox = [row[3], row[4], row[5], row[6]] if all(x is not None for x in row[3:7]) else None
                results.append({
                    "id": row[0],
                    "jersey_number": row[1],
                    "confidence": row[2],
                    "bbox": bbox,
                    "roster_entry_id": row[7],
                    "player_name": row[8],
                    "team_name": row[9],
                    "uniform_color": row[10],
                })
            return results

    @staticmethod
    def _compute_file_hash(file_path: str, chunk_size: int = 8192) -> str:
        """Compute SHA256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                sha256.update(chunk)
        return sha256.hexdigest()
