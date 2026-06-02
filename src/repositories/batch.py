"""BatchRepository - handles photo batch records."""

from pathlib import Path
from typing import Optional, List, Dict

from src.repositories._base import BaseRepository


class BatchRepository(BaseRepository):
    """Repository for photo_batches table."""

    def create_batch(
        self,
        source_folder: str,
        name: Optional[str] = None,
        team_name: Optional[str] = None,
        team_year: Optional[int] = None,
        tournament: Optional[str] = None,
    ) -> int:
        """Create a photo batch for an import folder and return its ID.

        If a batch for this source_folder already exists, returns its ID.
        """
        with self._lock:
            cursor = self._conn.cursor()
            # Check if batch already exists for this folder
            cursor.execute("SELECT id FROM photo_batches WHERE source_folder = ?", (source_folder,))
            existing = cursor.fetchone()
            if existing:
                return existing[0]
            # Auto-generate name from folder if not provided
            if not name:
                name = Path(source_folder).name
            cursor.execute("""
                INSERT INTO photo_batches (name, source_folder, team_name, team_year, tournament)
                VALUES (?, ?, ?, ?, ?)
            """, (name, source_folder, team_name, team_year, tournament))
            self._conn.commit()
            return cursor.lastrowid

    def get_batch(self, batch_id: int) -> Optional[Dict]:
        """Get a single batch by ID."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, name, source_folder, team_name, team_year, tournament, photo_count, created_at, updated_at
                FROM photo_batches
                WHERE id = ?
            """, (batch_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "name": row[1],
                "source_folder": row[2],
                "team_name": row[3],
                "team_year": row[4],
                "tournament": row[5],
                "photo_count": row[6],
                "created_at": row[7],
                "updated_at": row[8],
            }

    def get_all_batches(self) -> List[Dict]:
        """Get all photo batches."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, name, source_folder, team_name, team_year, tournament, photo_count, created_at, updated_at
                FROM photo_batches
                ORDER BY created_at DESC
            """)
            return [
                {
                    "id": row[0],
                    "name": row[1],
                    "source_folder": row[2],
                    "team_name": row[3],
                    "team_year": row[4],
                    "tournament": row[5],
                    "photo_count": row[6],
                    "created_at": row[7],
                    "updated_at": row[8],
                }
                for row in cursor.fetchall()
            ]

    def update_batch(
        self,
        batch_id: int,
        team_name: Optional[str] = None,
        team_year: Optional[int] = None,
        tournament: Optional[str] = None,
    ) -> None:
        """Update batch metadata."""
        with self._lock:
            cursor = self._conn.cursor()
            fields = []
            values = []
            if team_name is not None:
                fields.append("team_name = ?")
                values.append(team_name)
            if team_year is not None:
                fields.append("team_year = ?")
                values.append(team_year)
            if tournament is not None:
                fields.append("tournament = ?")
                values.append(tournament)
            if not fields:
                return
            fields.append("updated_at = CURRENT_TIMESTAMP")
            values.append(batch_id)
            cursor.execute(f"UPDATE photo_batches SET {', '.join(fields)} WHERE id = ?", values)
            self._conn.commit()

    def delete_batch(self, batch_id: int) -> int:
        """Delete a batch and unpin photos from it. Returns count of affected photos."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM photos WHERE batch_id = ?", (batch_id,))
            count = cursor.fetchone()[0]
            cursor.execute("UPDATE photos SET batch_id = NULL WHERE batch_id = ?", (batch_id,))
            cursor.execute("DELETE FROM photo_batches WHERE id = ?", (batch_id,))
            self._conn.commit()
            return count

    def get_photos_by_batch(self, batch_id: int) -> List[Dict]:
        """Get all photos in a batch."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, file_path, source_folder, batch_id, file_hash, file_size, created_at, ingested_at
                FROM photos
                WHERE batch_id = ?
                ORDER BY ingested_at DESC
            """, (batch_id,))
            return [
                {
                    "id": row[0],
                    "file_path": row[1],
                    "source_folder": row[2],
                    "batch_id": row[3],
                    "file_hash": row[4],
                    "file_size": row[5],
                    "created_at": row[6],
                    "ingested_at": row[7],
                }
                for row in cursor.fetchall()
            ]

    def get_batch_by_source_folder(self, source_folder: str) -> Optional[Dict]:
        """Get batch by source folder path."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, name, source_folder, team_name, team_year, tournament, photo_count, created_at, updated_at
                FROM photo_batches
                WHERE source_folder = ?
            """, (source_folder,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "name": row[1],
                "source_folder": row[2],
                "team_name": row[3],
                "team_year": row[4],
                "tournament": row[5],
                "photo_count": row[6],
                "created_at": row[7],
                "updated_at": row[8],
            }

    def update_batch_photo_count(self, batch_id: int) -> int:
        """Recalculate and update the photo count for a batch. Returns the new count."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM photos WHERE batch_id = ?", (batch_id,))
            count = cursor.fetchone()[0]
            cursor.execute("""
                UPDATE photo_batches
                SET photo_count = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (count, batch_id))
            self._conn.commit()
            return count
