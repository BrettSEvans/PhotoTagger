import pytest
import json
from pathlib import Path
from src.roster import RosterManager

@pytest.fixture
def tmp_roster(tmp_path):
    """Create a temporary roster file."""
    roster_data = {
        "team_name": "Test Team",
        "team_year": 2026,
        "jerseys": {
            "16": "Player Sixteen",
            "23": "Player Twenty-Three"
        }
    }
    roster_file = tmp_path / "test-roster-2026.json"
    roster_file.write_text(json.dumps(roster_data))
    return str(roster_file)

@pytest.fixture
def manager(tmp_roster):
    """Initialize RosterManager with test roster."""
    manager = RosterManager()
    manager.load_roster(tmp_roster)
    return manager

def test_roster_initialization():
    """Verify RosterManager initializes."""
    manager = RosterManager()
    assert manager is not None

def test_load_roster(tmp_roster):
    """Test loading a roster file."""
    manager = RosterManager()
    manager.load_roster(tmp_roster)
    assert "Test Team" in manager.rosters
    assert manager.rosters["Test Team"][2026] is not None

def test_get_player_name(manager):
    """Test looking up player by jersey."""
    name = manager.get_player_name("Test Team", 2026, "16")
    assert name == "Player Sixteen"

def test_get_player_name_not_found(manager):
    """Test lookup when player not found."""
    name = manager.get_player_name("Test Team", 2026, "99")
    assert name is None

def test_roster_validation_missing_team_name(tmp_path):
    """Test validation rejects invalid roster."""
    invalid_roster = {
        "team_year": 2026,
        "jerseys": {"16": "Player"}
    }
    roster_file = tmp_path / "invalid.json"
    roster_file.write_text(json.dumps(invalid_roster))

    manager = RosterManager()
    with pytest.raises(ValueError):
        manager.load_roster(str(roster_file))

def test_load_multiple_rosters(tmp_path):
    """Test loading multiple roster files."""
    manager = RosterManager()

    for year in [2024, 2025, 2026]:
        roster_data = {
            "team_name": "Team A",
            "team_year": year,
            "jerseys": {"16": f"Player {year}"}
        }
        roster_file = tmp_path / f"team-a-{year}.json"
        roster_file.write_text(json.dumps(roster_data))
        manager.load_roster(str(roster_file))

    # Should have Team A with 3 years
    assert 2024 in manager.rosters["Team A"]
    assert 2025 in manager.rosters["Team A"]
    assert 2026 in manager.rosters["Team A"]
