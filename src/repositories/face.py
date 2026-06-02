"""FaceRepository - handles face detection records."""

import json
from typing import Optional, List, Dict

from src.repositories._base import BaseRepository


class FaceRepository(BaseRepository):
    """Repository for faces table."""

    def add_face(self, photo_id: int, embedding: List[float], bbox: List[int], confidence: float,
                 sharpness: Optional[float] = None, face_size_ratio: Optional[float] = None,
                 quality_score: Optional[float] = None) -> int:
        """Add a detected face to the database."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO faces (photo_id, embedding, bbox_x0, bbox_y0, bbox_x1, bbox_y1, confidence, sharpness, face_size_ratio, quality_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (photo_id, json.dumps(embedding), bbox[0], bbox[1], bbox[2], bbox[3], confidence, sharpness, face_size_ratio, quality_score))
            self._conn.commit()
            return cursor.lastrowid

    def get_faces_by_photo(self, photo_id: int) -> List[Dict]:
        """Get all faces detected in a photo."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, photo_id, embedding, bbox_x0, bbox_y0, bbox_x1, bbox_y1, confidence
                FROM faces
                WHERE photo_id = ?
                ORDER BY confidence DESC
            """, (photo_id,))

            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row[0],
                    "photo_id": row[1],
                    "embedding": json.loads(row[2]),
                    "bbox": [row[3], row[4], row[5], row[6]],
                    "confidence": row[7]
                })
            return results

    def photo_has_faces(self, photo_id: int) -> bool:
        """Return whether a photo already has stored face detections."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT 1 FROM faces WHERE photo_id = ? LIMIT 1", (photo_id,))
            return cursor.fetchone() is not None

    def get_all_faces(self) -> List[Dict]:
        """Get all faces with their embeddings (for clustering)."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, photo_id, embedding, bbox_x0, bbox_y0, bbox_x1, bbox_y1, confidence, cluster_id, sharpness, face_size_ratio, quality_score
                FROM faces
                ORDER BY id
            """)
            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row[0],
                    "photo_id": row[1],
                    "embedding": json.loads(row[2]),
                    "bbox": [row[3], row[4], row[5], row[6]],
                    "confidence": row[7],
                    "cluster_id": row[8],
                    "sharpness": row[9],
                    "face_size_ratio": row[10],
                    "quality_score": row[11],
                })
            return results

    def get_face_by_id(self, face_id: int) -> Optional[Dict]:
        """Get a single face by its ID."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, photo_id, embedding, bbox_x0, bbox_y0, bbox_x1, bbox_y1, confidence, cluster_id
                FROM faces WHERE id = ?
            """, (face_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "photo_id": row[1],
                "embedding": json.loads(row[2]),
                "bbox": [row[3], row[4], row[5], row[6]],
                "confidence": row[7],
                "cluster_id": row[8],
            }

    def get_face_count(self) -> int:
        """Return total number of detected faces."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM faces")
            return cursor.fetchone()[0]

    def get_face_photo_location(self, face_id: int) -> Optional[Dict]:
        """Return photo_id and bbox for a single face — used for thumbnail modal links."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT photo_id, bbox_x0, bbox_y0, bbox_x1, bbox_y1 FROM faces WHERE id = ?",
                (face_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "photo_id": row[0],
                "face_bbox": [row[1], row[2], row[3], row[4]],
            }

    def deassign_faces(self, face_ids: List[int]):
        """Remove specific faces from their cluster and refresh affected cluster stats."""
        if not face_ids:
            return {"deassigned": 0, "affected_cluster_ids": [], "deleted_cluster_ids": []}
        with self._lock:
            cursor = self._conn.cursor()
            placeholders = ','.join('?' * len(face_ids))
            cursor.execute(
                f"SELECT DISTINCT cluster_id FROM faces WHERE id IN ({placeholders}) AND cluster_id IS NOT NULL",
                face_ids,
            )
            affected_cluster_ids = [row[0] for row in cursor.fetchall()]

            cursor.execute(f"UPDATE faces SET cluster_id = NULL WHERE id IN ({placeholders})", face_ids)
            deassigned_count = cursor.rowcount

            deleted_cluster_ids = []
            for cluster_id in affected_cluster_ids:
                cursor.execute("""
                    SELECT COUNT(*), COUNT(DISTINCT photo_id)
                    FROM faces
                    WHERE cluster_id = ?
                """, (cluster_id,))
                face_count, photo_count = cursor.fetchone()

                if face_count == 0:
                    cursor.execute("DELETE FROM player_clusters WHERE id = ?", (cluster_id,))
                    deleted_cluster_ids.append(cluster_id)
                    continue

                cursor.execute("""
                    SELECT id
                    FROM faces
                    WHERE cluster_id = ?
                    ORDER BY confidence DESC, id
                    LIMIT 1
                """, (cluster_id,))
                thumbnail_row = cursor.fetchone()
                thumbnail_face_id = thumbnail_row[0] if thumbnail_row else None
                cursor.execute("""
                    UPDATE player_clusters
                    SET face_count = ?, photo_count = ?, thumbnail_face_id = ?
                    WHERE id = ?
                """, (face_count, photo_count, thumbnail_face_id, cluster_id))

            self._conn.commit()
            return {
                "deassigned": deassigned_count,
                "affected_cluster_ids": affected_cluster_ids,
                "deleted_cluster_ids": deleted_cluster_ids,
            }
