"""
Unit tests for src/roster.py (RosterManager).

Covers load_roster, load_rosters_from_directory, get_player_name,
get_all_teams, and get_team_years.
"""

import json
import pytest
from pathlib import Path

from src.roster import RosterManager


@pytest.fixture
def manager():
    return RosterManager()


@pytest.fixture
def roster_file(tmp_path):
    """Write a valid roster JSON and return the path."""
    data = {
        "team_name": "Carleton (CUT)",
        "team_year": 2026,
        "jerseys": {"7": "Alice Smith", "15": "Bob Jones", "19": "Carol Lee"},
    }
    p = tmp_path / "cut_2026.json"
    p.write_text(json.dumps(data))
    return str(p)


# ---------------------------------------------------------------------------
# load_roster
# ---------------------------------------------------------------------------

class TestLoadRoster:
    def test_load_valid_roster(self, manager, roster_file):
        manager.load_roster(roster_file)
        assert "Carleton (CUT)" in manager.rosters

    def test_load_missing_file_raises(self, manager, tmp_path):
        with pytest.raises(FileNotFoundError):
            manager.load_roster(str(tmp_path / "nonexistent.json"))

    def test_load_missing_team_name_raises(self, manager, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text(json.dumps({"team_year": 2026, "jerseys": {}}))
        with pytest.raises(ValueError, match="team_name"):
            manager.load_roster(str(p))

    def test_load_missing_team_year_raises(self, manager, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text(json.dumps({"team_name": "X", "jerseys": {}}))
        with pytest.raises(ValueError, match="team_year"):
            manager.load_roster(str(p))

    def test_load_missing_jerseys_raises(self, manager, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text(json.dumps({"team_name": "X", "team_year": 2024}))
        with pytest.raises(ValueError, match="jerseys"):
            manager.load_roster(str(p))

    def test_load_invalid_json_raises(self, manager, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not valid json {{{")
        with pytest.raises(ValueError):
            manager.load_roster(str(p))

    def test_player_count_after_load(self, manager, roster_file):
        manager.load_roster(roster_file)
        year_data = manager.rosters["Carleton (CUT)"][2026]
        assert len(year_data) == 3


# ---------------------------------------------------------------------------
# load_rosters_from_directory
# ---------------------------------------------------------------------------

class TestLoadRostersFromDirectory:
    def test_load_from_empty_dir(self, manager, tmp_path):
        manager.load_rosters_from_directory(str(tmp_path))
        assert len(manager.rosters) == 0

    def test_load_from_nonexistent_dir(self, manager, tmp_path):
        with pytest.raises(NotADirectoryError):
            manager.load_rosters_from_directory(str(tmp_path / "nosuchdir"))

    def test_load_multiple_rosters(self, manager, tmp_path):
        for i in range(3):
            data = {"team_name": f"Team{i}", "team_year": 2024, "jerseys": {"7": f"Player{i}"}}
            (tmp_path / f"team{i}.json").write_text(json.dumps(data))
        manager.load_rosters_from_directory(str(tmp_path))
        assert len(manager.rosters) == 3

    def test_skips_invalid_roster_files(self, manager, tmp_path):
        (tmp_path / "bad.json").write_text("not json")
        data = {"team_name": "Good", "team_year": 2024, "jerseys": {"1": "Alice"}}
        (tmp_path / "good.json").write_text(json.dumps(data))
        manager.load_rosters_from_directory(str(tmp_path))
        assert "Good" in manager.rosters


# ---------------------------------------------------------------------------
# get_player_name
# ---------------------------------------------------------------------------

class TestGetPlayerName:
    def test_returns_player_name(self, manager, roster_file):
        manager.load_roster(roster_file)
        name = manager.get_player_name("Carleton (CUT)", 2026, "7")
        assert name == "Alice Smith"

    def test_returns_none_for_missing_team(self, manager):
        assert manager.get_player_name("NonExistent", 2026, "7") is None

    def test_returns_none_for_missing_year(self, manager, roster_file):
        manager.load_roster(roster_file)
        assert manager.get_player_name("Carleton (CUT)", 1999, "7") is None

    def test_returns_none_for_missing_jersey(self, manager, roster_file):
        manager.load_roster(roster_file)
        assert manager.get_player_name("Carleton (CUT)", 2026, "99") is None


# ---------------------------------------------------------------------------
# get_all_teams / get_team_years
# ---------------------------------------------------------------------------

class TestGetAllTeamsAndYears:
    def test_get_all_teams_empty(self, manager):
        assert manager.get_all_teams() == []

    def test_get_all_teams_after_load(self, manager, roster_file):
        manager.load_roster(roster_file)
        teams = manager.get_all_teams()
        assert "Carleton (CUT)" in teams

    def test_get_team_years_empty(self, manager):
        assert manager.get_team_years("NoTeam") == []

    def test_get_team_years_after_load(self, manager, roster_file):
        manager.load_roster(roster_file)
        years = manager.get_team_years("Carleton (CUT)")
        assert 2026 in years
