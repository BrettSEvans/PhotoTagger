"""RosterRepository - handles roster (player team roster) records."""

from typing import Optional, List, Dict

from src.repositories._base import BaseRepository


class RosterRepository(BaseRepository):
    """Repository for rosters table."""

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
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO rosters (team_name, team_year, jersey_number, player_name, uniform_color)
                VALUES (?, ?, ?, ?, ?)
            """, (team_name, team_year, jersey_number, player_name, uniform_color))
            self._conn.commit()

    def roster_entry_exists(self, team_name: str, team_year: int, jersey_number: str) -> bool:
        """Return whether a roster entry already exists for team/year/jersey."""
        with self._lock:
            cursor = self._conn.cursor()
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
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT player_name FROM rosters
                WHERE team_name = ? AND team_year = ? AND jersey_number = ?
            """, (team_name, team_year, jersey_number))
            result = cursor.fetchone()
            return result[0] if result else None

    def get_all_roster_entries(self) -> List[Dict]:
        """Return every roster row ordered by team then jersey number."""
        with self._lock:
            cursor = self._conn.cursor()
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
