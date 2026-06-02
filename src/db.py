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

    def init_schema(self):
        """Create database tables if they don't exist."""
        init_schema(self.conn)

    def add_photo(self, file_path: str, file_hash: Optional[str] = None, source_folder: Optional[str] = None, batch_id: Optional[int] = None) -> int:
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

        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO photos (file_path, file_hash, file_size, source_folder, batch_id)
                VALUES (?, ?, ?, ?, ?)
            """, (str(file_path), file_hash, file_size, source_folder, batch_id))
            self.conn.commit()

            return cursor.lastrowid

    def add_ocr_result(
        self,
        photo_id: int,
        jersey_number: Optional[str],
        confidence: float,
        raw_text: str,
        uniform_color: Optional[str] = None,
    ):
        """Add OCR extraction results for a photo."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO ocr_results (photo_id, jersey_number, uniform_color, confidence, raw_text)
                VALUES (?, ?, ?, ?, ?)
            """, (photo_id, jersey_number, uniform_color, confidence, raw_text))
            self.conn.commit()

    def get_photo_by_jersey(self, jersey_number: str) -> List[Dict]:
        """Find all photos matching a jersey number."""
        with self._lock:
            cursor = self.conn.cursor()
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
            cursor = self.conn.cursor()
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
            cursor = self.conn.cursor()
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
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM photos WHERE id = ?", (photo_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_photo_ocr(self, photo_id: int) -> Optional[Dict]:
        """Get OCR results for a specific photo."""
        with self._lock:
            cursor = self.conn.cursor()
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
            cursor = self.conn.cursor()
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
            cursor = self.conn.cursor()
            cursor.execute("SELECT id FROM photos WHERE file_hash = ?", (file_hash,))
            return cursor.fetchone() is not None

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
        """Add a player to the roster."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO rosters (team_name, team_year, jersey_number, player_name, uniform_color)
                VALUES (?, ?, ?, ?, ?)
            """, (team_name, team_year, jersey_number, player_name, uniform_color))
            self.conn.commit()

    def set_game_context(self, teams: List[Dict]):
        """Delegation stub: set game context via GameContextRepository."""
        return self.context.set_game_context(teams)

    def get_game_context(self) -> List[Dict]:
        """Delegation stub: get game context via GameContextRepository."""
        return self.context.get_game_context()

    def roster_entry_exists(self, team_name: str, team_year: int, jersey_number: str) -> bool:
        """Return whether a roster entry already exists for team/year/jersey."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT 1 FROM rosters
                WHERE team_name = ? AND team_year = ? AND jersey_number = ?
            """, (team_name, team_year, jersey_number))
            return cursor.fetchone() is not None

    def import_roster_entries(
        self,
        team_name: str,
        team_year: int,
        rows: List[Dict],
        duplicate_policy: str = "replace",
        uniform_color: Optional[str] = None,
    ) -> Dict:
        """Import roster rows with replace or skip duplicate handling."""
        if duplicate_policy not in {"replace", "skip"}:
            raise ValueError("duplicate_policy must be 'replace' or 'skip'")

        imported = 0
        skipped = 0
        failed = 0
        errors = []

        for idx, row in enumerate(rows, start=1):
            jersey = str(row.get("jersey_number", "")).strip()
            name = str(row.get("player_name", "")).strip()
            if not jersey or not name:
                failed += 1
                errors.append(f"Row {idx}: missing jersey_number or player_name")
                continue

            if duplicate_policy == "skip" and self.roster_entry_exists(team_name, team_year, jersey):
                skipped += 1
                continue

            try:
                self.add_roster_entry(team_name, team_year, jersey, name, uniform_color=uniform_color)
                imported += 1
            except Exception as exc:
                failed += 1
                errors.append(f"Row {idx}: {exc}")

        return {
            "success": failed == 0,
            "imported": imported,
            "skipped": skipped,
            "failed": failed,
            "errors": errors,
        }

    def get_player_name(self, team_name: str, team_year: int, jersey_number: str) -> Optional[str]:
        """Look up player name by jersey."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT player_name FROM rosters
                WHERE team_name = ? AND team_year = ? AND jersey_number = ?
            """, (team_name, team_year, jersey_number))
            result = cursor.fetchone()
            return result[0] if result else None

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
        """Return every roster row ordered by team then jersey number."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT r.id, r.team_name, r.team_year, r.jersey_number, r.player_name, r.uniform_color,
                       (
                         SELECT pc.thumbnail_face_id
                         FROM player_clusters pc
                         WHERE (
                            pc.roster_entry_id = r.id
                            OR (
                              pc.roster_entry_id IS NULL
                              AND pc.player_name = r.player_name
                            )
                         )
                           AND pc.thumbnail_face_id IS NOT NULL
                         ORDER BY pc.photo_count DESC, pc.face_count DESC, pc.id
                         LIMIT 1
                       ) AS thumbnail_face_id
                FROM rosters r
                ORDER BY team_name, CAST(jersey_number AS INTEGER)
            """)
            return [
                {"id": r[0], "team_name": r[1], "team_year": r[2],
                 "jersey_number": r[3], "player_name": r[4], "uniform_color": r[5], "thumbnail_face_id": r[6]}
                for r in cursor.fetchall()
            ]

    def delete_roster_entry(self, entry_id: int):
        """Delete a single roster row by primary key."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM rosters WHERE id = ?", (entry_id,))
            self.conn.commit()

    def update_roster_entry(self, entry_id: int, **kwargs) -> Dict:
        """Update a roster entry with any combination of fields.

        Args:
            entry_id: The roster entry ID to update
            player_name: (optional) New player name
            jersey_number: (optional) New jersey number
            team_name: (optional) New team name
            team_year: (optional) New team year
            uniform_color: (optional) New uniform color

        Returns:
            The updated roster entry dict

        Raises:
            ValueError: If entry not found or unique constraint would be violated
            sqlite3.IntegrityError: If database constraint is violated
        """
        with self._lock:
            cursor = self.conn.cursor()

            # Get current entry to compare
            cursor.execute(
                "SELECT id, team_name, team_year, jersey_number, player_name, uniform_color FROM rosters WHERE id = ?",
                (entry_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Roster entry {entry_id} not found")

            current = {
                "id": row[0],
                "team_name": row[1],
                "team_year": row[2],
                "jersey_number": row[3],
                "player_name": row[4],
                "uniform_color": row[5],
            }

            # Build update dict with new values, keeping current values for unspecified fields
            updates = {
                "team_name": kwargs.get("team_name", current["team_name"]),
                "team_year": kwargs.get("team_year", current["team_year"]),
                "jersey_number": kwargs.get("jersey_number", current["jersey_number"]),
                "player_name": kwargs.get("player_name", current["player_name"]),
                "uniform_color": kwargs.get("uniform_color", current["uniform_color"]),
            }

            # Validate required fields
            if not updates["player_name"] or not updates["player_name"].strip():
                raise ValueError("player_name cannot be empty")
            if not updates["jersey_number"] or not updates["jersey_number"].strip():
                raise ValueError("jersey_number cannot be empty")

            # Check for unique constraint violation (only if the key fields changed)
            key_fields_changed = (
                updates["team_name"] != current["team_name"] or
                updates["team_year"] != current["team_year"] or
                updates["jersey_number"] != current["jersey_number"]
            )

            if key_fields_changed:
                cursor.execute(
                    """SELECT 1 FROM rosters
                    WHERE id != ? AND team_name = ? AND team_year = ? AND jersey_number = ?""",
                    (entry_id, updates["team_name"], updates["team_year"], updates["jersey_number"])
                )
                if cursor.fetchone():
                    raise ValueError(
                        f"Roster entry already exists for {updates['team_name']} "
                        f"({updates['team_year']}) jersey #{updates['jersey_number']}"
                    )

            # Perform update
            cursor.execute(
                """UPDATE rosters
                SET player_name = ?, jersey_number = ?, team_name = ?, team_year = ?, uniform_color = ?
                WHERE id = ?""",
                (updates["player_name"], updates["jersey_number"], updates["team_name"],
                 updates["team_year"], updates["uniform_color"], entry_id)
            )
            self.conn.commit()

            # Return updated entry
            return {
                "id": entry_id,
                "team_name": updates["team_name"],
                "team_year": updates["team_year"],
                "jersey_number": updates["jersey_number"],
                "player_name": updates["player_name"],
                "uniform_color": updates["uniform_color"],
            }

    def search_roster(self, query: str) -> List[Dict]:
        """Fuzzy search roster by player name or jersey number (max 10 results)."""
        with self._lock:
            cursor = self.conn.cursor()
            pattern = f"%{query}%"
            cursor.execute("""
                SELECT id, team_name, jersey_number, player_name, uniform_color
                FROM rosters
                WHERE player_name LIKE ? OR jersey_number LIKE ?
                ORDER BY CAST(jersey_number AS INTEGER)
                LIMIT 10
            """, (pattern, pattern))
            return [
                {"id": r[0], "team_name": r[1], "jersey_number": r[2], "player_name": r[3], "uniform_color": r[4]}
                for r in cursor.fetchall()
            ]

    def get_roster_entry_by_id(self, entry_id: int) -> Optional[Dict]:
        """Return one roster row by primary key."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, team_name, team_year, jersey_number, player_name, uniform_color
                FROM rosters
                WHERE id = ?
            """, (entry_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "team_name": row[1],
                "team_year": row[2],
                "jersey_number": row[3],
                "player_name": row[4],
                "uniform_color": row[5],
            }

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
        """Return counts: total photos, auto-tagged (jersey→roster match), needs review."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM photos")
            total = cursor.fetchone()[0]

            tagged = 0
            needs_review = 0
            context = self.get_game_context()
            for row in self._get_latest_ocr_rows(cursor):
                matches = self.resolve_roster_candidates(
                    row["jersey_number"], row.get("uniform_color"), context=context
                )
                if len(matches) == 1:
                    tagged += 1
                else:
                    needs_review += 1

            return {"total_photos": total, "tagged": tagged, "needs_review": needs_review}

    def get_confirmed_photos(self, limit: int = 60, offset: int = 0) -> List[Dict]:
        """Photos where OCR jersey and game context resolve to one roster player."""
        with self._lock:
            cursor = self.conn.cursor()
            confirmed = []
            context = self.get_game_context()
            for row in self._get_latest_ocr_rows(cursor):
                matches = self.resolve_roster_candidates(
                    row["jersey_number"], row.get("uniform_color"), context=context
                )
                if len(matches) == 1:
                    match = matches[0]
                    confirmed.append({
                        "id": row["id"],
                        "file_path": row["file_path"],
                        "jersey_number": row["jersey_number"],
                        "player_name": match["player_name"],
                        "team_name": match["team_name"],
                        "uniform_color": match["uniform_color"],
                        "confidence": row["confidence"],
                    })
            return confirmed[offset:offset + limit]

    def get_review_photos(self, limit: int = 60, offset: int = 0) -> List[Dict]:
        """Photos where OCR found a jersey but roster context is missing or ambiguous."""
        with self._lock:
            cursor = self.conn.cursor()
            review = []
            context = self.get_game_context()
            for row in self._get_latest_ocr_rows(cursor):
                matches = self.resolve_roster_candidates(
                    row["jersey_number"], row.get("uniform_color"), context=context
                )
                if len(matches) != 1:
                    review.append({
                        "id": row["id"],
                        "file_path": row["file_path"],
                        "jersey_number": row["jersey_number"],
                        "uniform_color": row.get("uniform_color"),
                        "confidence": row["confidence"],
                        "roster_candidates": matches,
                    })
            return review[offset:offset + limit]

    def _get_latest_ocr_rows(self, cursor) -> List[Dict]:
        """Return latest non-empty OCR row per photo, ordered by confidence."""
        cursor.execute("""
            SELECT p.id, p.file_path, o.jersey_number, o.uniform_color, o.confidence, o.raw_text
            FROM photos p
            JOIN ocr_results o ON o.photo_id = p.id
            WHERE o.jersey_number IS NOT NULL
              AND o.id = (
                  SELECT MAX(o2.id)
                  FROM ocr_results o2
                  WHERE o2.photo_id = p.id
                    AND o2.jersey_number IS NOT NULL
              )
            ORDER BY o.confidence DESC
        """)
        return [dict(row) for row in cursor.fetchall()]

    def resolve_roster_candidates(self, jersey_number: str, uniform_color: Optional[str] = None, context: Optional[List[Dict]] = None) -> List[Dict]:
        """Resolve roster candidates for a jersey within active game context and optional uniform color.

        Pass a pre-fetched ``context`` (from ``get_game_context()``) when calling this in a loop
        to avoid re-querying the game context for every row.
        """
        cursor = self.conn.cursor()
        if context is None:
            context = self.get_game_context()

        if context:
            candidates = []
            for team in context:
                cursor.execute("""
                    SELECT id, team_name, team_year, jersey_number, player_name, uniform_color
                    FROM rosters
                    WHERE team_name = ? AND team_year = ? AND jersey_number = ?
                """, (team["team_name"], team["team_year"], str(jersey_number)))
                for row in cursor.fetchall():
                    roster_color = team.get("uniform_color") or row[5]
                    candidates.append({
                        "id": row[0],
                        "team_name": row[1],
                        "team_year": row[2],
                        "jersey_number": row[3],
                        "player_name": row[4],
                        "uniform_color": roster_color,
                    })
        else:
            cursor.execute("""
                SELECT id, team_name, team_year, jersey_number, player_name, uniform_color
                FROM rosters
                WHERE jersey_number = ?
            """, (str(jersey_number),))
            candidates = [
                {
                    "id": row[0],
                    "team_name": row[1],
                    "team_year": row[2],
                    "jersey_number": row[3],
                    "player_name": row[4],
                    "uniform_color": row[5],
                }
                for row in cursor.fetchall()
            ]

        if not uniform_color:
            return candidates

        matched = []
        for candidate in candidates:
            score = self._color_match_score(uniform_color, candidate.get("uniform_color"))
            if score > 0:
                matched.append({**candidate, "match_score": score})
        return matched

    @staticmethod
    def _color_match_score(detected: Optional[str], roster: Optional[str]) -> float:
        """Score whether two uniform color labels are compatible."""
        if not detected or not roster:
            return 0.0

        detected = detected.lower().strip()
        roster = roster.lower().strip()
        if detected == roster:
            return 1.0

        color_families = {
            "red": {"red", "crimson", "dark red", "maroon", "burgundy"},
            "white": {"white", "light gray", "off-white", "cream"},
            "blue": {"blue", "navy", "royal blue", "dark blue"},
            "black": {"black", "dark gray", "charcoal"},
            "yellow": {"yellow", "gold", "orange-yellow"},
            "green": {"green", "dark green", "forest green"},
        }

        detected_family = next((family for family, colors in color_families.items() if detected in colors), None)
        roster_family = next((family for family, colors in color_families.items() if roster in colors), None)
        if detected_family and detected_family == roster_family:
            return 0.9
        return 0.0

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
