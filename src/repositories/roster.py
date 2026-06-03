"""RosterRepository - handles roster (player team roster) records."""

from typing import Optional, List, Dict

from src.repositories._base import BaseRepository


class RosterRepository(BaseRepository):
    """Repository for rosters table."""

    def add_roster_entry(
        self,
        team_name: str,
        team_year: int,
        jersey_number: Optional[int],
        player_name: str,
        uniform_color: Optional[str] = None,
    ):
        """Add a player to the roster. jersey_number may be None (e.g. coaches)."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO rosters (team_name, team_year, jersey_number, player_name, uniform_color)
                VALUES (?, ?, ?, ?, ?)
            """, (team_name, team_year, jersey_number, player_name, uniform_color))
            self._conn.commit()

    def roster_entry_exists(self, team_name: str, team_year: int, jersey_number: Optional[int]) -> bool:
        """Return whether a roster entry already exists for team/year/jersey."""
        with self._lock:
            cursor = self._conn.cursor()
            if jersey_number is None:
                cursor.execute("""
                    SELECT 1 FROM rosters
                    WHERE team_name = ? AND team_year = ? AND jersey_number IS NULL
                """, (team_name, team_year))
            else:
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
            jersey_raw = row.get("jersey_number")
            jersey: Optional[int] = None
            if jersey_raw is not None and str(jersey_raw).strip() != "":
                try:
                    jersey = int(str(jersey_raw).strip())
                except (ValueError, TypeError):
                    failed += 1
                    errors.append(f"Row {idx}: jersey_number must be an integer, got {jersey_raw!r}")
                    continue
            name = str(row.get("player_name", "")).strip()
            if not name:
                failed += 1
                errors.append(f"Row {idx}: missing player_name")
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

    def get_player_name(self, team_name: str, team_year: int, jersey_number: int) -> Optional[str]:
        """Look up player name by jersey number (integer). Returns None for NULL jersey entries."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT player_name FROM rosters
                WHERE team_name = ? AND team_year = ? AND jersey_number IS NOT NULL AND CAST(jersey_number AS INTEGER) = ?
            """, (team_name, team_year, int(jersey_number)))
            result = cursor.fetchone()
            return result[0] if result else None

    def get_all_roster_entries(self) -> List[Dict]:
        """Return every roster row ordered by team then jersey number.

        Optimized query: avoid N+1 correlated subqueries by using a UNION and GROUP BY.
        For each roster entry, find the best matching cluster (by roster_entry_id or player_name),
        then pick the cluster with the highest photo_count.
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT r.id, r.team_name, r.team_year, r.jersey_number, r.player_name, r.uniform_color,
                       COALESCE(
                         (SELECT pc.thumbnail_face_id FROM player_clusters pc
                          WHERE pc.roster_entry_id = r.id AND pc.thumbnail_face_id IS NOT NULL
                          ORDER BY pc.photo_count DESC, pc.face_count DESC, pc.id LIMIT 1),
                         (SELECT pc.thumbnail_face_id FROM player_clusters pc
                          WHERE pc.roster_entry_id IS NULL AND pc.player_name = r.player_name
                            AND pc.thumbnail_face_id IS NOT NULL
                          ORDER BY pc.photo_count DESC, pc.face_count DESC, pc.id LIMIT 1)
                       ) AS thumbnail_face_id
                FROM rosters r
                ORDER BY r.team_name, CAST(r.jersey_number AS INTEGER)
            """)
            return [
                {"id": r[0], "team_name": r[1], "team_year": r[2],
                 "jersey_number": r[3], "player_name": r[4], "uniform_color": r[5], "thumbnail_face_id": r[6]}
                for r in cursor.fetchall()
            ]

    def delete_roster_entry(self, entry_id: int):
        """Delete a single roster row by primary key."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("DELETE FROM rosters WHERE id = ?", (entry_id,))
            self._conn.commit()

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
            cursor = self._conn.cursor()

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
            # jersey_number: parse to int if provided and non-empty, allow None
            raw_jersey = kwargs.get("jersey_number", current["jersey_number"])
            if raw_jersey is None or str(raw_jersey).strip() == "":
                new_jersey: Optional[int] = None
            else:
                try:
                    new_jersey = int(str(raw_jersey).strip())
                except (ValueError, TypeError):
                    raise ValueError(f"jersey_number must be an integer, got {raw_jersey!r}")

            updates = {
                "team_name": kwargs.get("team_name", current["team_name"]),
                "team_year": kwargs.get("team_year", current["team_year"]),
                "jersey_number": new_jersey,
                "player_name": kwargs.get("player_name", current["player_name"]),
                "uniform_color": kwargs.get("uniform_color", current["uniform_color"]),
            }

            # Validate required fields (jersey_number is optional)
            if not updates["player_name"] or not updates["player_name"].strip():
                raise ValueError("player_name cannot be empty")

            # Check for unique constraint violation (only if the key fields changed)
            key_fields_changed = (
                updates["team_name"] != current["team_name"] or
                updates["team_year"] != current["team_year"] or
                updates["jersey_number"] != current["jersey_number"]
            )

            if key_fields_changed and updates["jersey_number"] is not None:
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
            self._conn.commit()

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
            cursor = self._conn.cursor()
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
            cursor = self._conn.cursor()
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

    def resolve_roster_candidates(self, jersey_number: str, uniform_color: Optional[str] = None, context: Optional[List[Dict]] = None) -> List[Dict]:
        """Resolve roster candidates for a jersey within active game context and optional uniform color.

        Pass a pre-fetched ``context`` (from ``get_game_context()``) when calling this in a loop
        to avoid re-querying the game context for every row.
        """
        cursor = self._conn.cursor()
        if context is None:
            # Need to get context from somewhere — for now, return empty list
            # In practice, ReviewService will always pass context
            context = []

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

    def find_by_jersey_color_and_team(
        self,
        jersey_number: int,
        team_name: str,
        jersey_color: str,
        year: int,
    ) -> Optional[Dict]:
        """Find a roster entry by all four matching criteria: jersey, team, color, year.

        Args:
            jersey_number: Jersey number as integer (e.g. 31). NULL entries are never matched.
            team_name: Team name (e.g. "Carleton")
            jersey_color: Uniform color (e.g. "red")
            year: Tournament year

        Returns:
            Roster entry dict if found, None otherwise
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, team_name, team_year, jersey_number, player_name, uniform_color
                FROM rosters
                WHERE jersey_number IS NOT NULL
                  AND CAST(jersey_number AS INTEGER) = ?
                  AND team_name = ?
                  AND team_year = ?
                  AND uniform_color = ?
                LIMIT 1
            """, (int(jersey_number), team_name, year, jersey_color))
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
