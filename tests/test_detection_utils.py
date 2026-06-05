"""
Unit tests for src/detection_utils.py.

Covers:
  - normalize_jersey_number
  - load_image
  - match_to_roster
  - get_game_context
"""

import io
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np

from src import detection_utils


# ---------------------------------------------------------------------------
# normalize_jersey_number
# ---------------------------------------------------------------------------

class TestNormalizeJerseyNumber:
    """Tests for detection_utils.normalize_jersey_number."""

    def test_plain_number_returned_as_is(self):
        assert detection_utils.normalize_jersey_number("19") == "19"

    def test_number_with_trailing_text(self):
        # Only leading digits are kept
        assert detection_utils.normalize_jersey_number("31 DE") == "31"

    def test_leading_zeros_preserved(self):
        assert detection_utils.normalize_jersey_number("07") == "07"

    def test_empty_string_returns_none(self):
        assert detection_utils.normalize_jersey_number("") is None

    def test_none_returns_none(self):
        assert detection_utils.normalize_jersey_number(None) is None

    def test_text_only_returns_none(self):
        assert detection_utils.normalize_jersey_number("ABC") is None

    def test_leading_space_stripped(self):
        assert detection_utils.normalize_jersey_number("  42") == "42"

    def test_single_digit(self):
        assert detection_utils.normalize_jersey_number("7") == "7"

    def test_number_followed_by_punctuation(self):
        assert detection_utils.normalize_jersey_number("15.") == "15"


# ---------------------------------------------------------------------------
# load_image
# ---------------------------------------------------------------------------

class TestLoadImage:
    """Tests for detection_utils.load_image."""

    def test_nonexistent_path_returns_none(self):
        result = detection_utils.load_image("/nonexistent/path/file.jpg")
        assert result is None

    def test_empty_path_returns_none(self):
        result = detection_utils.load_image("")
        assert result is None

    def test_none_path_returns_none(self):
        result = detection_utils.load_image(None)
        assert result is None

    def test_valid_image_returns_ndarray(self, tmp_path):
        """Write a minimal JPEG and verify load_image returns an ndarray."""
        from PIL import Image
        img_path = tmp_path / "test.jpg"
        pil = Image.new("RGB", (32, 32), color=(200, 100, 50))
        pil.save(str(img_path), format="JPEG")

        result = detection_utils.load_image(str(img_path))
        assert result is not None
        assert isinstance(result, np.ndarray)
        assert result.shape[2] == 3  # BGR channels


# ---------------------------------------------------------------------------
# get_game_context
# ---------------------------------------------------------------------------

class TestGetGameContext:
    """Tests for detection_utils.get_game_context."""

    def test_returns_list_on_success(self):
        db = MagicMock()
        db.context.get_game_context.return_value = [
            {"team_name": "Team A", "team_year": 2024, "uniform_color": "red"}
        ]
        result = detection_utils.get_game_context(db)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_returns_empty_list_on_exception(self):
        db = MagicMock()
        db.context.get_game_context.side_effect = Exception("DB error")
        result = detection_utils.get_game_context(db)
        assert result == []

    def test_passes_through_context_data(self):
        teams = [
            {"team_name": "CUT", "team_year": 2026, "uniform_color": "black"},
            {"team_name": "Sundodgers", "team_year": 2026, "uniform_color": "white"},
        ]
        db = MagicMock()
        db.context.get_game_context.return_value = teams
        result = detection_utils.get_game_context(db)
        assert result == teams


# ---------------------------------------------------------------------------
# match_to_roster
# ---------------------------------------------------------------------------

class TestMatchToRoster:
    """Tests for detection_utils.match_to_roster."""

    def _mock_db(self, entry=None):
        db = MagicMock()
        db.roster.find_by_jersey_color_and_team.return_value = entry
        return db

    def test_returns_match_when_found(self):
        entry = {
            "id": 1, "player_name": "Alice", "team_name": "Team A",
            "team_year": 2024, "jersey_number": 23, "uniform_color": "red"
        }
        db = self._mock_db(entry)
        result = detection_utils.match_to_roster(
            db, jersey_number="23", value_type="jersey_number",
            team_name="Team A", jersey_color="red", year=2024,
        )
        assert result is not None
        assert result["player_name"] == "Alice"

    def test_returns_none_when_not_found(self):
        db = self._mock_db(None)
        result = detection_utils.match_to_roster(
            db, jersey_number="99", value_type="jersey_number",
            team_name="Team A", jersey_color="red", year=2024,
        )
        assert result is None

    def test_returns_none_for_unknown_value_type(self):
        db = self._mock_db()
        result = detection_utils.match_to_roster(
            db, jersey_number="23", value_type="face_embedding",
            team_name="Team A", jersey_color="red", year=2024,
        )
        assert result is None
        # Should not have touched the DB
        db.roster.find_by_jersey_color_and_team.assert_not_called()

    def test_returns_none_when_missing_criteria(self):
        db = self._mock_db()
        # Missing team_name
        result = detection_utils.match_to_roster(
            db, jersey_number="23", value_type="jersey_number",
            team_name=None, jersey_color="red", year=2024,
        )
        assert result is None

    def test_returns_none_for_non_integer_jersey(self):
        db = self._mock_db()
        result = detection_utils.match_to_roster(
            db, jersey_number="abc", value_type="jersey_number",
            team_name="Team A", jersey_color="red", year=2024,
        )
        assert result is None

    def test_converts_jersey_number_to_int(self):
        """match_to_roster passes jersey_number as int to the repo."""
        entry = {"id": 5, "player_name": "Bob"}
        db = self._mock_db(entry)
        detection_utils.match_to_roster(
            db, jersey_number="007", value_type="jersey_number",
            team_name="Team A", jersey_color="blue", year=2025,
        )
        db.roster.find_by_jersey_color_and_team.assert_called_once_with(
            jersey_number=7, team_name="Team A", jersey_color="blue", year=2025
        )

    def test_returns_none_on_db_exception(self):
        db = MagicMock()
        db.roster.find_by_jersey_color_and_team.side_effect = RuntimeError("oops")
        result = detection_utils.match_to_roster(
            db, jersey_number="23", value_type="jersey_number",
            team_name="Team A", jersey_color="red", year=2024,
        )
        assert result is None
