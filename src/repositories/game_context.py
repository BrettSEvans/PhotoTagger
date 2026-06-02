"""GameContextRepository - handles game context (team colors/years)."""

from typing import List, Dict

from src.repositories._base import BaseRepository


class GameContextRepository(BaseRepository):
    """Repository for game_context_teams table."""

    def set_game_context(self, teams: List[Dict]):
        """Replace the active game context with teams and their uniform colors."""
        with self._lock:
            cursor = self._conn.cursor()
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
            self._conn.commit()

    def get_game_context(self) -> List[Dict]:
        """Return the active game context teams in display order."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT team_name, team_year, uniform_color
                FROM game_context_teams
                ORDER BY position, id
            """)
            return [
                {"team_name": row[0], "team_year": row[1], "uniform_color": row[2]}
                for row in cursor.fetchall()
            ]
