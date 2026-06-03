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

    def get_all_player_clusters(self, min_photos: int = 1, min_prominence: float = 0.0) -> List[Dict]:
        """Get all player clusters with stats.

        Optional review filtering separates real, taggable players from noise:
          - min_photos: drop clusters seen in fewer than this many photos (one-off
            "zombie" mis-detections).
          - min_prominence: drop clusters whose LARGEST face is below this size ratio
            (all-background clusters that never get a foreground appearance).
        Clusters already assigned to a player (player_name set) are always returned.
        Defaults (1, 0.0) apply no filtering.
        """
        with self._lock:
            cursor = self._conn.cursor()
            from src.config import CLOSE_UP_PROMINENCE
            cursor.execute("""
                SELECT id, face_count, photo_count, thumbnail_face_id, created_at,
                       player_name, jersey_number, roster_entry_id,
                       (SELECT MAX(f.face_size_ratio) FROM faces f WHERE f.cluster_id = pc.id) as max_face_size,
                       (SELECT COUNT(*) FROM faces f WHERE f.cluster_id = pc.id
                        AND f.jersey_color IS NOT NULL AND f.jersey_color != 'black'
                        AND (f.jersey_color_conf IS NULL OR f.jersey_color_conf >= 0.45)) as team_jersey_faces
                FROM player_clusters pc
                ORDER BY photo_count DESC
            """)
            result = []
            for row in cursor.fetchall():
                player_name = row[5]
                photo_count = row[2] or 0
                max_face_size = row[8] or 0.0
                team_jersey_faces = row[9] or 0
                # Always surface clusters the user has already assigned
                if player_name is None:
                    # Check prominence for all unassigned clusters
                    if min_prominence > 0 and max_face_size < min_prominence:
                        continue
                    # For singletons, also allow if no team jersey AND small faces
                    # (only close-ups can pass with small faces)
                    if photo_count < min_photos:
                        if team_jersey_faces == 0 and max_face_size < CLOSE_UP_PROMINENCE:
                            continue
                result.append({
                    "id": row[0],
                    "face_count": row[1],
                    "photo_count": row[2],
                    "thumbnail_face_id": row[3],
                    "created_at": row[4],
                    "player_name": player_name,
                    "jersey_number": row[6],
                    "roster_entry_id": row[7],
                })
            return result

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

    def consolidate_player_clusters(self, player_name: str) -> Dict:
        """Merge all clusters with the same player_name into one primary cluster.
        Keeps the cluster with most faces, merges others into it, deletes secondaries."""
        if not player_name:
            return {"merged": False, "reason": "No player_name provided"}

        with self._lock:
            cursor = self._conn.cursor()
            # Find all clusters with this player_name
            cursor.execute("""
                SELECT id, face_count FROM player_clusters
                WHERE player_name = ?
                ORDER BY face_count DESC
            """, (player_name,))
            clusters = cursor.fetchall()

            if len(clusters) <= 1:
                return {"merged": False, "reason": "Only one or zero clusters found"}

            # Primary cluster is the one with most faces
            primary_id = clusters[0][0]
            secondary_ids = [c[0] for c in clusters[1:]]

            # Move all faces from secondary clusters to primary
            for secondary_id in secondary_ids:
                cursor.execute("""
                    UPDATE faces SET cluster_id = ? WHERE cluster_id = ?
                """, (primary_id, secondary_id))

            # Delete secondary clusters
            placeholders = ','.join('?' * len(secondary_ids))
            cursor.execute(f"DELETE FROM player_clusters WHERE id IN ({placeholders})", secondary_ids)

            self._conn.commit()
            return {
                "merged": True,
                "primary_id": primary_id,
                "merged_count": len(secondary_ids),
                "secondary_ids": secondary_ids
            }
