import pytest
from pathlib import Path
from src.player_identifier import PlayerIdentifier
from src.roster import RosterManager
from src.db import Database


@pytest.fixture
def db():
    """Initialize database."""
    return Database(":memory:")


@pytest.fixture
def roster_manager():
    """Initialize roster manager."""
    return RosterManager()


@pytest.fixture
def identifier(db):
    """Initialize PlayerIdentifier."""
    return PlayerIdentifier(db=db)


@pytest.fixture
def photo_path():
    """Get path to test photo."""
    return "photos/DSC_0256-sm.JPG"


class TestPlayerIdentifierInitialization:
    """Test PlayerIdentifier initialization."""

    def test_initializes_with_db(self, identifier):
        """PlayerIdentifier should initialize with database."""
        assert identifier.db is not None
        assert identifier.player_detector is not None
        assert identifier.uniform_detector is not None
        assert identifier.ocr_engine is not None
        assert identifier.roster_manager is not None

    def test_initializes_without_db(self):
        """PlayerIdentifier should work without database."""
        identifier = PlayerIdentifier(db=None)
        assert identifier.db is None
        assert identifier.ocr_engine is None  # OCR requires DB
        assert identifier.player_detector is not None

    def test_has_required_methods(self, identifier):
        """PlayerIdentifier should have required methods."""
        assert hasattr(identifier, 'identify_players_in_photo')
        assert hasattr(identifier, '_extract_jersey')
        assert hasattr(identifier, '_detect_color_from_region')
        assert hasattr(identifier, '_match_roster')
        assert hasattr(identifier, '_color_match_score')
        assert hasattr(identifier, '_calculate_combined_confidence')


class TestColorMatching:
    """Test color matching logic."""

    def test_exact_color_match(self, identifier):
        """Exact color match should return 1.0."""
        score = identifier._color_match_score('red', 'red')
        assert score == 1.0

    def test_case_insensitive_match(self, identifier):
        """Color matching should be case-insensitive."""
        score = identifier._color_match_score('RED', 'red')
        assert score == 1.0

    def test_whitespace_insensitive_match(self, identifier):
        """Color matching should handle whitespace."""
        score = identifier._color_match_score('  red  ', 'red')
        assert score == 1.0

    def test_color_family_match_red(self, identifier):
        """Red color family members should match."""
        for color in ['crimson', 'dark red', 'maroon']:
            score = identifier._color_match_score('red', color)
            assert score == 0.9

    def test_color_family_match_white(self, identifier):
        """White color family members should match."""
        for color in ['light gray', 'off-white', 'cream']:
            score = identifier._color_match_score('white', color)
            assert score == 0.9

    def test_color_family_match_blue(self, identifier):
        """Blue color family members should match."""
        for color in ['navy', 'royal blue', 'dark blue']:
            score = identifier._color_match_score('blue', color)
            assert score == 0.9

    def test_no_color_match(self, identifier):
        """Non-matching colors should return 0.0."""
        score = identifier._color_match_score('red', 'blue')
        assert score == 0.0

    def test_both_sides_family_match(self, identifier):
        """Should match family if either side is in family."""
        score = identifier._color_match_score('crimson', 'dark red')
        assert score == 0.9


class TestConfidenceCalculation:
    """Test combined confidence calculation."""

    def test_combined_confidence_weights(self, identifier):
        """Combined confidence should apply weights correctly."""
        # jersey=1.0, color=1.0, match=1.0 → 1.0
        conf = identifier._calculate_combined_confidence(1.0, 1.0, 1.0)
        assert conf == 1.0

        # jersey=0.0, color=0.0, match=0.0 → 0.0
        conf = identifier._calculate_combined_confidence(0.0, 0.0, 0.0)
        assert conf == 0.0

    def test_combined_confidence_jersey_heavy(self, identifier):
        """Jersey should have highest weight (40%)."""
        # Only jersey matches
        conf = identifier._calculate_combined_confidence(1.0, 0.0, 0.0)
        assert conf == 1.0 * 0.40

        # Only color matches
        conf = identifier._calculate_combined_confidence(0.0, 1.0, 0.0)
        assert conf == 1.0 * 0.35

        # Only match matches
        conf = identifier._calculate_combined_confidence(0.0, 0.0, 1.0)
        assert conf == 1.0 * 0.25

    def test_combined_confidence_balanced(self, identifier):
        """All factors equal should give weighted average."""
        conf = identifier._calculate_combined_confidence(0.8, 0.8, 0.8)
        expected = 0.8 * (0.40 + 0.35 + 0.25)
        assert abs(conf - expected) < 0.001

    def test_combined_confidence_capped_at_1(self, identifier):
        """Combined confidence should never exceed 1.0."""
        conf = identifier._calculate_combined_confidence(1.5, 1.5, 1.5)
        assert conf <= 1.0


class TestIdentificationWorkflow:
    """Test full identification workflow."""

    def test_identify_players_missing_image(self, identifier, roster_manager):
        """identify_players_in_photo should return None for missing image."""
        result = identifier.identify_players_in_photo(
            "photos/nonexistent.jpg",
            roster_manager=roster_manager
        )
        assert result is None

    def test_identify_players_returns_list(self, identifier, roster_manager, photo_path):
        """identify_players_in_photo should return list or empty list."""
        if not Path(photo_path).exists():
            pytest.skip("Test photo not available")

        result = identifier.identify_players_in_photo(
            photo_path,
            roster_manager=roster_manager
        )

        assert result is not None
        assert isinstance(result, list)

    def test_identify_players_result_structure(self, identifier, roster_manager, photo_path):
        """Identified players should have complete structure."""
        if not Path(photo_path).exists():
            pytest.skip("Test photo not available")

        result = identifier.identify_players_in_photo(
            photo_path,
            roster_manager=roster_manager,
            min_confidence=0.0  # Lower threshold to get any results
        )

        if result:  # Only check structure if we got results
            for player in result:
                assert 'face_id' in player
                assert 'jersey' in player
                assert 'shirt_color' in player
                assert 'team' in player
                assert 'player_name' in player
                assert 'location' in player
                assert 'jersey_confidence' in player
                assert 'color_confidence' in player
                assert 'match_confidence' in player
                assert 'combined_confidence' in player
                assert 'bbox' in player
                assert 'bbox_expanded' in player

    def test_identify_players_confidence_threshold(self, identifier, roster_manager, photo_path):
        """Min confidence threshold should filter results."""
        if not Path(photo_path).exists():
            pytest.skip("Test photo not available")

        # Get all results with low threshold
        results_low = identifier.identify_players_in_photo(
            photo_path,
            roster_manager=roster_manager,
            min_confidence=0.0
        )

        # Get results with high threshold
        results_high = identifier.identify_players_in_photo(
            photo_path,
            roster_manager=roster_manager,
            min_confidence=0.95
        )

        # Higher threshold should give same or fewer results
        assert len(results_high) <= len(results_low)

    def test_identify_players_team_year_parameter(self, identifier, roster_manager, photo_path):
        """Should respect team_year parameter."""
        if not Path(photo_path).exists():
            pytest.skip("Test photo not available")

        # Test with different year
        result_2026 = identifier.identify_players_in_photo(
            photo_path,
            roster_manager=roster_manager,
            team_year=2026,
            min_confidence=0.0
        )

        result_2027 = identifier.identify_players_in_photo(
            photo_path,
            roster_manager=roster_manager,
            team_year=2027,
            min_confidence=0.0
        )

        # Results might differ if different rosters loaded for different years
        assert isinstance(result_2026, list)
        assert isinstance(result_2027, list)


class TestRosterMatching:
    """Test roster matching logic."""

    def test_match_roster_returns_dict_or_none(self, identifier, roster_manager):
        """_match_roster should return dict or None."""
        result = identifier._match_roster(
            jersey='1',
            shirt_color='red',
            roster_manager=roster_manager,
            team_year=2026
        )

        assert result is None or isinstance(result, dict)

    def test_match_roster_structure(self, identifier):
        """Matched roster entry should have required fields."""
        # Create a simple roster
        roster = RosterManager()
        roster.rosters = {
            'Team A': {
                2026: {
                    'uniform_color': 'red',
                    'jerseys': {'1': 'John Doe'}
                }
            }
        }

        result = identifier._match_roster(
            jersey='1',
            shirt_color='red',
            roster_manager=roster,
            team_year=2026
        )

        assert result is not None
        assert 'team_name' in result
        assert 'player_name' in result
        assert 'match_score' in result

    def test_match_roster_invalid_jersey(self, identifier):
        """Non-existent jersey should return None."""
        roster = RosterManager()
        roster.rosters = {
            'Team A': {
                2026: {
                    'uniform_color': 'red',
                    'jerseys': {'1': 'John Doe'}
                }
            }
        }

        result = identifier._match_roster(
            jersey='99',  # Non-existent
            shirt_color='red',
            roster_manager=roster,
            team_year=2026
        )

        assert result is None

    def test_match_roster_invalid_year(self, identifier):
        """Non-existent year should return None."""
        roster = RosterManager()
        roster.rosters = {
            'Team A': {
                2026: {
                    'uniform_color': 'red',
                    'jerseys': {'1': 'John Doe'}
                }
            }
        }

        result = identifier._match_roster(
            jersey='1',
            shirt_color='red',
            roster_manager=roster,
            team_year=2027  # Non-existent
        )

        assert result is None

    def test_match_roster_color_matching(self, identifier):
        """Should prefer color-matched rosters."""
        roster = RosterManager()
        roster.rosters = {
            'Team Red': {
                2026: {
                    'uniform_color': 'red',
                    'jerseys': {'1': 'Red Player'}
                }
            },
            'Team Blue': {
                2026: {
                    'uniform_color': 'blue',
                    'jerseys': {'1': 'Blue Player'}
                }
            },
        }

        # When looking for jersey 1 in red, should match Team Red
        result = identifier._match_roster(
            jersey='1',
            shirt_color='red',
            roster_manager=roster,
            team_year=2026
        )

        assert result is not None
        assert result['team_name'] == 'Team Red'
        assert result['player_name'] == 'Red Player'


class TestOCRIntegration:
    """Test OCR integration (when available)."""

    def test_extract_jersey_without_ocr(self):
        """_extract_jersey should handle missing OCR gracefully."""
        identifier = PlayerIdentifier(db=None)  # No DB = no OCR
        import numpy as np

        img = np.ones((100, 100, 3), dtype=np.uint8) * 255
        jersey, conf = identifier._extract_jersey(img, [10, 10, 50, 50])

        assert jersey is None
        assert conf == 0.0


class TestIntegrationScenarios:
    """Integration tests combining multiple components."""

    def test_spectator_filtering(self, identifier, roster_manager, photo_path):
        """Should filter out spectators in background."""
        if not Path(photo_path).exists():
            pytest.skip("Test photo not available")

        # Get all people (should include field + background)
        all_people = identifier.player_detector.detect_players(photo_path)
        background_people = [p for p in all_people if p['location'] == 'background']

        # Identified players should only be from field
        result = identifier.identify_players_in_photo(
            photo_path,
            roster_manager=roster_manager,
            min_confidence=0.0
        )

        for player in result:
            assert player['location'] == 'field'

    def test_multi_team_detection(self, identifier):
        """Should detect players from different teams."""
        roster = RosterManager()
        roster.rosters = {
            'Team Red': {
                2026: {
                    'uniform_color': 'red',
                    'jerseys': {'1': 'Red #1', '2': 'Red #2'}
                }
            },
            'Team White': {
                2026: {
                    'uniform_color': 'white',
                    'jerseys': {'1': 'White #1', '2': 'White #2'}
                }
            },
        }

        # Both teams have jersey 1
        red_result = identifier._match_roster('1', 'red', roster, 2026)
        white_result = identifier._match_roster('1', 'white', roster, 2026)

        assert red_result['team_name'] == 'Team Red'
        assert white_result['team_name'] == 'Team White'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
