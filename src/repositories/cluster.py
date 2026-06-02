"""ClusterRepository - handles player cluster records."""

import json
from typing import Optional, List, Dict

from src.repositories._base import BaseRepository


class ClusterRepository(BaseRepository):
    """Repository for player_clusters table."""

    def clear_clusters(self):
        """Remove all cluster assignments and reset ID sequence (reset before re-clustering)."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("UPDATE faces SET cluster_id = NULL")
            cursor.execute("DELETE FROM player_clusters")
            # Reset auto-increment so next cluster starts at ID 1 (fresh session)
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='player_clusters'")
            self._conn.commit()

    def add_player_cluster(self, face_count: int, photo_count: int, thumbnail_face_id: Optional[int]) -> int:
        """Insert a player cluster and return its ID."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO player_clusters (face_count, photo_count, thumbnail_face_id)
                VALUES (?, ?, ?)
            """, (face_count, photo_count, thumbnail_face_id))
            self._conn.commit()
            return cursor.lastrowid

    def assign_face_to_cluster(self, face_id: int, cluster_id: int):
        """Set the cluster_id on a face row."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("UPDATE faces SET cluster_id = ? WHERE id = ?", (cluster_id, face_id))
            self._conn.commit()

    def get_all_player_clusters(self) -> List[Dict]:
        """Get all player clusters with stats.

        Subject detection gates faces before they're assigned a cluster_id, so every
        persisted cluster already contains only real (player) faces — no empty-cluster
        filtering needed here.
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, face_count, photo_count, thumbnail_face_id, created_at,
                       player_name, jersey_number, roster_entry_id
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
                    "roster_entry_id": row[7],
                }
                for row in cursor.fetchall()
            ]

    def get_photos_by_cluster(self, cluster_id: int, min_face_confidence: float = 0.0) -> List[Dict]:
        """Get all photos that contain a face in this cluster.

        Faces are gated by subject detection at clustering time, so cluster
        membership alone determines what shows here.
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT DISTINCT p.id, p.file_path, p.ingested_at,
                       f.id as face_id, f.bbox_x0, f.bbox_y0, f.bbox_x1, f.bbox_y1, f.confidence
                FROM photos p
                JOIN faces f ON f.photo_id = p.id
                WHERE f.cluster_id = ?
                  AND f.confidence >= ?
                ORDER BY p.id
            """, (cluster_id, min_face_confidence))
            return [
                {
                    "id": row[0],
                    "photo_id": row[0],
                    "file_path": row[1],
                    "added_at": row[2],
                    "face_id": row[3],
                    "face_bbox": [row[4], row[5], row[6], row[7]],
                    "face_confidence": row[8],
                }
                for row in cursor.fetchall()
            ]

    def get_cluster_by_id(self, cluster_id: int) -> Optional[Dict]:
        """Get a single player cluster by ID."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, face_count, photo_count, thumbnail_face_id, created_at,
                       player_name, jersey_number, roster_entry_id
                FROM player_clusters WHERE id = ?
            """, (cluster_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "face_count": row[1],
                "photo_count": row[2],
                "thumbnail_face_id": row[3],
                "created_at": row[4],
                "player_name": row[5],
                "jersey_number": row[6],
                "roster_entry_id": row[7],
            }

    def get_cluster_face_embeddings(self, cluster_id: int) -> List[List[float]]:
        """Return raw embedding vectors for all faces in a cluster."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT embedding FROM faces WHERE cluster_id = ?", (cluster_id,)
            )
            return [json.loads(row[0]) for row in cursor.fetchall()]

    def get_unidentified_clusters_with_embeddings(self) -> List[Dict]:
        """Return all unidentified clusters together with their face embeddings."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, face_count, thumbnail_face_id
                FROM player_clusters
                WHERE player_name IS NULL
                ORDER BY face_count DESC
            """)
            clusters = [
                {"id": row[0], "face_count": row[1], "thumbnail_face_id": row[2], "embeddings": []}
                for row in cursor.fetchall()
            ]
            for cluster in clusters:
                cursor.execute(
                    "SELECT embedding FROM faces WHERE cluster_id = ?", (cluster["id"],)
                )
                cluster["embeddings"] = [json.loads(row[0]) for row in cursor.fetchall()]
            return clusters

    def assign_cluster_to_player(
        self,
        cluster_id: int,
        player_name: str,
        jersey_number: str,
        roster_entry_id: Optional[int] = None,
    ):
        """Attach a roster player identity to a face cluster."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE player_clusters SET player_name = ?, jersey_number = ?, roster_entry_id = ?
                WHERE id = ?
            """, (player_name, jersey_number, roster_entry_id, cluster_id))
            self._conn.commit()
