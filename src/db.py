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

    def add_photo(self, file_path: str, file_hash: Optional[str] = None, source_folder: Optional[str] = None, batch_id: Optional[int] = None) -> int:
        """Delegation stub: add photo via PhotoRepository."""
        return self.photos.add_photo(file_path, file_hash, source_folder, batch_id)

    def add_ocr_result(
        self,
        photo_id: int,
        jersey_number: Optional[str],
        confidence: float,
        raw_text: str,
        uniform_color: Optional[str] = None,
    ):
        """Delegation stub: add OCR result via PhotoRepository."""
        return self.photos.add_ocr_result(photo_id, jersey_number, confidence, raw_text, uniform_color)

    def get_photo_by_jersey(self, jersey_number: str) -> List[Dict]:
        """Delegation stub: get photos by jersey via PhotoRepository."""
        return self.photos.get_photo_by_jersey(jersey_number)

    def count_photos(self) -> int:
        """Delegation stub: count photos via PhotoRepository."""
        return self.photos.count_photos()

    def get_all_photos(self, limit: Optional[int] = None, offset: int = 0) -> List[Dict]:
        """Delegation stub: get all photos via PhotoRepository."""
        return self.photos.get_all_photos(limit, offset)

    def get_photo_by_id(self, photo_id: int) -> Optional[Dict]:
        """Delegation stub: get photo by ID via PhotoRepository."""
        return self.photos.get_photo_by_id(photo_id)

    def get_photo_ocr(self, photo_id: int) -> Optional[Dict]:
        """Delegation stub: get photo OCR via PhotoRepository."""
        return self.photos.get_photo_ocr(photo_id)

    def get_latest_ocr_by_photo_ids(self, photo_ids: List[int]) -> Dict[int, Dict]:
        """Delegation stub: get latest OCR by photo IDs via PhotoRepository."""
        return self.photos.get_latest_ocr_by_photo_ids(photo_ids)

    def photo_exists(self, file_hash: str) -> bool:
        """Delegation stub: check if photo exists via PhotoRepository."""
        return self.photos.photo_exists(file_hash)

    def create_processing_job(self, job_type: str, payload: Optional[Dict] = None) -> int:
        """Delegation stub: create a processing job via JobRepository."""
        return self.jobs.create_processing_job(job_type, payload)

    def update_processing_job(
        self,
        job_id: int,
        *,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        result: Optional[Dict] = None,
        error: Optional[str] = None,
    ):
        """Delegation stub: update a processing job via JobRepository."""
        return self.jobs.update_processing_job(job_id, status=status, progress=progress, result=result, error=error)

    def get_processing_job(self, job_id: int) -> Optional[Dict]:
        """Delegation stub: get a processing job via JobRepository."""
        return self.jobs.get_processing_job(job_id)

    def add_face(self, photo_id: int, embedding: List[float], bbox: List[int], confidence: float,
                 sharpness: Optional[float] = None, face_size_ratio: Optional[float] = None) -> int:
        """Delegation stub: add face via FaceRepository."""
        return self.faces.add_face(photo_id, embedding, bbox, confidence, sharpness, face_size_ratio)

    def get_faces_by_photo(self, photo_id: int) -> List[Dict]:
        """Delegation stub: get faces by photo via FaceRepository."""
        return self.faces.get_faces_by_photo(photo_id)

    def photo_has_faces(self, photo_id: int) -> bool:
        """Delegation stub: check if photo has faces via FaceRepository."""
        return self.faces.photo_has_faces(photo_id)

    def add_roster_entry(
        self,
        team_name: str,
        team_year: int,
        jersey_number: str,
        player_name: str,
        uniform_color: Optional[str] = None,
    ):
        """Delegation stub: add roster entry via RosterRepository."""
        return self.roster.add_roster_entry(team_name, team_year, jersey_number, player_name, uniform_color)

    def set_game_context(self, teams: List[Dict]):
        """Delegation stub: set game context via GameContextRepository."""
        return self.context.set_game_context(teams)

    def get_game_context(self) -> List[Dict]:
        """Delegation stub: get game context via GameContextRepository."""
        return self.context.get_game_context()

    def roster_entry_exists(self, team_name: str, team_year: int, jersey_number: str) -> bool:
        """Delegation stub: check roster entry existence via RosterRepository."""
        return self.roster.roster_entry_exists(team_name, team_year, jersey_number)

    def import_roster_entries(
        self,
        team_name: str,
        team_year: int,
        rows: List[Dict],
        duplicate_policy: str = "replace",
        uniform_color: Optional[str] = None,
    ) -> Dict:
        """Delegation stub: import roster entries via RosterRepository."""
        return self.roster.import_roster_entries(team_name, team_year, rows, duplicate_policy, uniform_color)

    def get_player_name(self, team_name: str, team_year: int, jersey_number: str) -> Optional[str]:
        """Delegation stub: get player name via RosterRepository."""
        return self.roster.get_player_name(team_name, team_year, jersey_number)

    def get_assigned_player_for_photo(self, photo_id: int) -> Optional[str]:
        """Get the player name assigned to a photo via cluster assignment.

        Returns the player_name if the photo contains a face in an assigned cluster,
        else None.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT DISTINCT pc.player_name
                FROM faces f
                JOIN player_clusters pc ON f.cluster_id = pc.id
                WHERE f.photo_id = ? AND pc.player_name IS NOT NULL
                LIMIT 1
            """, (photo_id,))
            result = cursor.fetchone()
            return result[0] if result else None

    def get_all_faces(self) -> List[Dict]:
        """Delegation stub: get all faces via FaceRepository."""
        return self.faces.get_all_faces()

    def get_face_by_id(self, face_id: int) -> Optional[Dict]:
        """Delegation stub: get face by ID via FaceRepository."""
        return self.faces.get_face_by_id(face_id)

    def clear_clusters(self):
        """Delegation stub: clear clusters via ClusterRepository."""
        return self.clusters.clear_clusters()

    def add_player_cluster(self, face_count: int, photo_count: int, thumbnail_face_id: Optional[int]) -> int:
        """Delegation stub: add player cluster via ClusterRepository."""
        return self.clusters.add_player_cluster(face_count, photo_count, thumbnail_face_id)

    def assign_face_to_cluster(self, face_id: int, cluster_id: int):
        """Delegation stub: assign face to cluster via ClusterRepository."""
        return self.clusters.assign_face_to_cluster(face_id, cluster_id)

    def get_all_player_clusters(self) -> List[Dict]:
        """Delegation stub: get all player clusters via ClusterRepository."""
        return self.clusters.get_all_player_clusters()

    def get_photos_by_cluster(self, cluster_id: int, min_face_confidence: float = 0.0) -> List[Dict]:
        """Delegation stub: get photos by cluster via ClusterRepository."""
        return self.clusters.get_photos_by_cluster(cluster_id, min_face_confidence)

    def get_face_count(self) -> int:
        """Delegation stub: get face count via FaceRepository."""
        return self.faces.get_face_count()

    # ── Roster CRUD ─────────────────────────────────────────────────────────────

    def get_all_roster_entries(self) -> List[Dict]:
        """Delegation stub: get all roster entries via RosterRepository."""
        return self.roster.get_all_roster_entries()

    def delete_roster_entry(self, entry_id: int):
        """Delegation stub: delete roster entry via RosterRepository."""
        return self.roster.delete_roster_entry(entry_id)

    def update_roster_entry(self, entry_id: int, **kwargs) -> Dict:
        """Delegation stub: update roster entry via RosterRepository."""
        return self.roster.update_roster_entry(entry_id, **kwargs)

    def search_roster(self, query: str) -> List[Dict]:
        """Delegation stub: search roster via RosterRepository."""
        return self.roster.search_roster(query)

    def get_roster_entry_by_id(self, entry_id: int) -> Optional[Dict]:
        """Delegation stub: get roster entry by ID via RosterRepository."""
        return self.roster.get_roster_entry_by_id(entry_id)

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

    # ── Processing summary ───────────────────────────────────────────────────────

    def get_processing_summary(self) -> Dict:
        """Delegation stub: get processing summary via ReviewService."""
        return self.review.get_processing_summary()

    def get_confirmed_photos(self, limit: int = 60, offset: int = 0) -> List[Dict]:
        """Delegation stub: get confirmed photos via ReviewService."""
        return self.review.get_confirmed_photos(limit, offset)

    def get_review_photos(self, limit: int = 60, offset: int = 0) -> List[Dict]:
        """Delegation stub: get review photos via ReviewService."""
        return self.review.get_review_photos(limit, offset)

    def _get_latest_ocr_rows(self, cursor) -> List[Dict]:
        """Delegation stub: get latest OCR rows via ReviewService."""
        return self.review._get_latest_ocr_rows(cursor)

    def resolve_roster_candidates(self, jersey_number: str, uniform_color: Optional[str] = None, context: Optional[List[Dict]] = None) -> List[Dict]:
        """Delegation stub: resolve roster candidates via RosterRepository."""
        return self.roster.resolve_roster_candidates(jersey_number, uniform_color, context)

    @staticmethod
    def _color_match_score(detected: Optional[str], roster: Optional[str]) -> float:
        """Delegation stub: color match score via RosterRepository."""
        return RosterRepository._color_match_score(detected, roster)

    def deassign_faces(self, face_ids: List[int]):
        """Delegation stub: deassign faces via FaceRepository."""
        return self.faces.deassign_faces(face_ids)

    def get_cluster_by_id(self, cluster_id: int) -> Optional[Dict]:
        """Delegation stub: get cluster by id via ClusterRepository."""
        return self.clusters.get_cluster_by_id(cluster_id)

    def get_face_photo_location(self, face_id: int) -> Optional[Dict]:
        """Delegation stub: get face photo location via FaceRepository."""
        return self.faces.get_face_photo_location(face_id)

    def get_cluster_face_embeddings(self, cluster_id: int) -> List[List[float]]:
        """Delegation stub: get cluster face embeddings via ClusterRepository."""
        return self.clusters.get_cluster_face_embeddings(cluster_id)

    def get_unidentified_clusters_with_embeddings(self) -> List[Dict]:
        """Delegation stub: get unidentified clusters with embeddings via ClusterRepository."""
        return self.clusters.get_unidentified_clusters_with_embeddings()

    def assign_cluster_to_player(
        self,
        cluster_id: int,
        player_name: str,
        jersey_number: str,
        roster_entry_id: Optional[int] = None,
    ):
        """Delegation stub: assign cluster to player via ClusterRepository."""
        return self.clusters.assign_cluster_to_player(cluster_id, player_name, jersey_number, roster_entry_id)

    # ── Photo Batches (Import Groups) ───────────────────────────────────────

    def create_batch(
        self,
        source_folder: str,
        name: Optional[str] = None,
        team_name: Optional[str] = None,
        team_year: Optional[int] = None,
        tournament: Optional[str] = None,
    ) -> int:
        """Delegation stub: create batch via BatchRepository."""
        return self.batches.create_batch(source_folder, name, team_name, team_year, tournament)

    def get_batch(self, batch_id: int) -> Optional[Dict]:
        """Delegation stub: get batch via BatchRepository."""
        return self.batches.get_batch(batch_id)

    def get_all_batches(self) -> List[Dict]:
        """Delegation stub: get all batches via BatchRepository."""
        return self.batches.get_all_batches()

    def update_batch(
        self,
        batch_id: int,
        team_name: Optional[str] = None,
        team_year: Optional[int] = None,
        tournament: Optional[str] = None,
    ) -> None:
        """Delegation stub: update batch via BatchRepository."""
        return self.batches.update_batch(batch_id, team_name, team_year, tournament)

    def delete_batch(self, batch_id: int) -> int:
        """Delegation stub: delete batch via BatchRepository."""
        return self.batches.delete_batch(batch_id)

    def get_photos_by_batch(self, batch_id: int) -> List[Dict]:
        """Delegation stub: get photos by batch via BatchRepository."""
        return self.batches.get_photos_by_batch(batch_id)

    def get_batch_by_source_folder(self, source_folder: str) -> Optional[Dict]:
        """Delegation stub: get batch by source folder via BatchRepository."""
        return self.batches.get_batch_by_source_folder(source_folder)

    def update_batch_photo_count(self, batch_id: int) -> int:
        """Delegation stub: update batch photo count via BatchRepository."""
        return self.batches.update_batch_photo_count(batch_id)

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
