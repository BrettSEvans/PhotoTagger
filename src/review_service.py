"""ReviewService - cross-domain queries for photo review and processing status."""

from typing import Optional, List, Dict

from src.repositories.photo import PhotoRepository
from src.repositories.roster import RosterRepository
from src.repositories.game_context import GameContextRepository


class ReviewService:
    """Service for cross-domain review queries.

    Composes photo, roster, and game context repositories to provide
    high-level review queries without forcing repo-to-repo dependencies.
    """

    def __init__(self, photos: PhotoRepository, roster: RosterRepository, context: GameContextRepository):
        """Initialize with repository instances."""
        self.photos = photos
        self.roster = roster
        self.context = context

    def get_processing_summary(self) -> Dict:
        """Return counts: total photos, auto-tagged (jersey→roster match), needs review."""
        # Statements on the shared connection must be serialized — see the note in
        # RosterRepository.resolve_roster_candidates. The lock is scoped to the
        # queries (which materialize their rows) so the per-row resolution loop
        # below does not hold it while the dashboard polls.
        with self.photos._lock:
            cursor = self.photos._conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM photos")
            total = cursor.fetchone()[0]
            ocr_rows = self._get_latest_ocr_rows(cursor)

        tagged = 0
        needs_review = 0
        context = self.context.get_game_context()
        for row in ocr_rows:
            matches = self.roster.resolve_roster_candidates(
                row["jersey_number"], row.get("uniform_color"), context=context
            )
            if len(matches) == 1:
                tagged += 1
            else:
                needs_review += 1

        return {"total_photos": total, "tagged": tagged, "needs_review": needs_review}

    def get_confirmed_photos(self, limit: int = 60, offset: int = 0) -> List[Dict]:
        """Photos where OCR jersey and game context resolve to one roster player."""
        with self.photos._lock:
            ocr_rows = self._get_latest_ocr_rows(self.photos._conn.cursor())
        confirmed = []
        context = self.context.get_game_context()
        for row in ocr_rows:
            matches = self.roster.resolve_roster_candidates(
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
        with self.photos._lock:
            ocr_rows = self._get_latest_ocr_rows(self.photos._conn.cursor())
        review = []
        context = self.context.get_game_context()
        for row in ocr_rows:
            matches = self.roster.resolve_roster_candidates(
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
