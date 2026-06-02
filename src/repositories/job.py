"""JobRepository - handles processing job records."""

import json
from typing import Optional, Dict

from src.repositories._base import BaseRepository


class JobRepository(BaseRepository):
    """Repository for processing_jobs table."""

    def create_processing_job(self, job_type: str, payload: Optional[Dict] = None) -> int:
        """Create a local processing job and return its ID."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO processing_jobs (type, status, progress, payload)
                VALUES (?, 'queued', 0, ?)
            """, (job_type, json.dumps(payload or {})))
            self._conn.commit()
            return cursor.lastrowid

    def update_processing_job(
        self,
        job_id: int,
        *,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        result: Optional[Dict] = None,
        error: Optional[str] = None,
    ):
        """Update a processing job status/result."""
        fields = []
        values = []
        if status is not None:
            fields.append("status = ?")
            values.append(status)
            if status == "running":
                fields.append("started_at = COALESCE(started_at, CURRENT_TIMESTAMP)")
            if status in {"succeeded", "failed"}:
                fields.append("finished_at = CURRENT_TIMESTAMP")
        if progress is not None:
            fields.append("progress = ?")
            values.append(max(0, min(100, int(progress))))
        if result is not None:
            fields.append("result = ?")
            values.append(json.dumps(result))
        if error is not None:
            fields.append("error = ?")
            values.append(error)
        if not fields:
            return

        with self._lock:
            cursor = self._conn.cursor()
            values.append(job_id)
            cursor.execute(f"UPDATE processing_jobs SET {', '.join(fields)} WHERE id = ?", values)
            self._conn.commit()

    def get_processing_job(self, job_id: int) -> Optional[Dict]:
        """Return one processing job by ID."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, type, status, progress, payload, result, error,
                       created_at, started_at, finished_at
                FROM processing_jobs
                WHERE id = ?
            """, (job_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "type": row[1],
                "status": row[2],
                "progress": row[3],
                "payload": json.loads(row[4]) if row[4] else {},
                "result": json.loads(row[5]) if row[5] else None,
                "error": row[6],
                "created_at": row[7],
                "started_at": row[8],
                "finished_at": row[9],
            }
