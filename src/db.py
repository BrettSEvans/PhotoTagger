import sqlite3
import hashlib
import threading
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

class Database:
    def __init__(self, db_path: str = "photo_catalog.db"):
        """Initialize database connection."""
        self.db_path = db_path
        self._lock = threading.RLock()
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
                uniform_color TEXT,
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
                uniform_color TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(team_name, team_year, jersey_number)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS game_context_teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_name TEXT NOT NULL,
                team_year INTEGER NOT NULL,
                uniform_color TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0
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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processing_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                progress INTEGER NOT NULL DEFAULT 0,
                payload TEXT,
                result TEXT,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                finished_at TIMESTAMP
            )
        """)

        # Add cluster_id column to faces if it doesn't exist yet
        try:
            cursor.execute("ALTER TABLE faces ADD COLUMN cluster_id INTEGER REFERENCES player_clusters(id)")
        except Exception:
            pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE ocr_results ADD COLUMN uniform_color TEXT")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE rosters ADD COLUMN uniform_color TEXT")
        except Exception:
            pass

        # Add player_name / jersey_number to player_clusters if not present
        try:
            cursor.execute("ALTER TABLE player_clusters ADD COLUMN player_name TEXT")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE player_clusters ADD COLUMN jersey_number TEXT")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE player_clusters ADD COLUMN roster_entry_id INTEGER REFERENCES rosters(id)")
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

    def add_ocr_result(
        self,
        photo_id: int,
        jersey_number: Optional[str],
        confidence: float,
        raw_text: str,
        uniform_color: Optional[str] = None,
    ):
        """Add OCR extraction results for a photo."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO ocr_results (photo_id, jersey_number, uniform_color, confidence, raw_text)
            VALUES (?, ?, ?, ?, ?)
        """, (photo_id, jersey_number, uniform_color, confidence, raw_text))
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

    def create_processing_job(self, job_type: str, payload: Optional[Dict] = None) -> int:
        """Create a local processing job and return its ID."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO processing_jobs (type, status, progress, payload)
                VALUES (?, 'queued', 0, ?)
            """, (job_type, json.dumps(payload or {})))
            self.conn.commit()
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
            cursor = self.conn.cursor()
            values.append(job_id)
            cursor.execute(f"UPDATE processing_jobs SET {', '.join(fields)} WHERE id = ?", values)
            self.conn.commit()

    def get_processing_job(self, job_id: int) -> Optional[Dict]:
        """Return one processing job by ID."""
        with self._lock:
            cursor = self.conn.cursor()
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

    def photo_has_faces(self, photo_id: int) -> bool:
        """Return whether a photo already has stored face detections."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT 1 FROM faces WHERE photo_id = ? LIMIT 1", (photo_id,))
            return cursor.fetchone() is not None

    def add_roster_entry(
        self,
        team_name: str,
        team_year: int,
        jersey_number: str,
        player_name: str,
        uniform_color: Optional[str] = None,
    ):
        """Add a player to the roster."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO rosters (team_name, team_year, jersey_number, player_name, uniform_color)
            VALUES (?, ?, ?, ?, ?)
        """, (team_name, team_year, jersey_number, player_name, uniform_color))
        self.conn.commit()

    def set_game_context(self, teams: List[Dict]):
        """Replace the active game context with teams and their uniform colors."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM game_context_teams")
            for position, team in enumerate(teams):
                team_name = str(team.get("team_name", "")).strip()
                team_year = int(team.get("team_year", 2026))
                uniform_color = str(team.get("uniform_color", "")).strip().lower()
                if not team_name or not uniform_color:
                    continue
                cursor.execute("""
                    INSERT INTO game_context_teams (team_name, team_year, uniform_color, position)
                    VALUES (?, ?, ?, ?)
                """, (team_name, team_year, uniform_color, position))
            self.conn.commit()

    def get_game_context(self) -> List[Dict]:
        """Return the active game context teams in display order."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT team_name, team_year, uniform_color
                FROM game_context_teams
                ORDER BY position, id
            """)
            return [
                {"team_name": row[0], "team_year": row[1], "uniform_color": row[2]}
                for row in cursor.fetchall()
            ]

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
        """Get all photos that contain a face in this cluster."""
        with self._lock:
            cursor = self.conn.cursor()
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

    # ── Processing summary ───────────────────────────────────────────────────────

    def get_processing_summary(self) -> Dict:
        """Return counts: total photos, auto-tagged (jersey→roster match), needs review."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM photos")
            total = cursor.fetchone()[0]

            tagged = 0
            needs_review = 0
            for row in self._get_latest_ocr_rows(cursor):
                matches = self.resolve_roster_candidates(row["jersey_number"], row.get("uniform_color"))
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
            for row in self._get_latest_ocr_rows(cursor):
                matches = self.resolve_roster_candidates(row["jersey_number"], row.get("uniform_color"))
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
            for row in self._get_latest_ocr_rows(cursor):
                matches = self.resolve_roster_candidates(row["jersey_number"], row.get("uniform_color"))
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

    def resolve_roster_candidates(self, jersey_number: str, uniform_color: Optional[str] = None) -> List[Dict]:
        """Resolve roster candidates for a jersey within active game context and optional uniform color."""
        cursor = self.conn.cursor()
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
        """Remove specific faces from their cluster and refresh affected cluster stats."""
        if not face_ids:
            return {"deassigned": 0, "affected_cluster_ids": [], "deleted_cluster_ids": []}
        with self._lock:
            cursor = self.conn.cursor()
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

            self.conn.commit()
            return {
                "deassigned": deassigned_count,
                "affected_cluster_ids": affected_cluster_ids,
                "deleted_cluster_ids": deleted_cluster_ids,
            }

    def assign_cluster_to_player(
        self,
        cluster_id: int,
        player_name: str,
        jersey_number: str,
        roster_entry_id: Optional[int] = None,
    ):
        """Attach a roster player identity to a face cluster."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE player_clusters SET player_name = ?, jersey_number = ?, roster_entry_id = ?
                WHERE id = ?
            """, (player_name, jersey_number, roster_entry_id, cluster_id))
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
