import json
import logging
from pathlib import Path
from typing import Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RosterManager:
    """Manage team rosters and player name lookups."""

    def __init__(self):
        """Initialize empty roster store."""
        # Structure: {team_name: {year: {jersey: player_name}}}
        self.rosters: Dict[str, Dict[int, Dict[str, str]]] = {}

    def load_roster(self, roster_file: str):
        """
        Load a roster from JSON file.

        Args:
            roster_file: Path to roster JSON file

        Raises:
            ValueError: If roster format is invalid
        """
        path = Path(roster_file)
        if not path.exists():
            raise FileNotFoundError(f"Roster file not found: {roster_file}")

        try:
            with open(path, 'r') as f:
                data = json.load(f)

            # Validate required fields
            if 'team_name' not in data:
                raise ValueError("Roster missing 'team_name' field")
            if 'team_year' not in data:
                raise ValueError("Roster missing 'team_year' field")
            if 'jerseys' not in data:
                raise ValueError("Roster missing 'jerseys' field")

            team_name = data['team_name']
            team_year = int(data['team_year'])
            jerseys = data['jerseys']

            # Store roster
            if team_name not in self.rosters:
                self.rosters[team_name] = {}

            self.rosters[team_name][team_year] = jerseys
            logger.info(f"Loaded roster: {team_name} ({team_year}) - {len(jerseys)} players")

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in roster file: {e}")

    def load_rosters_from_directory(self, directory: str):
        """
        Load all roster JSON files from a directory.

        Args:
            directory: Path to directory containing roster files
        """
        path = Path(directory)
        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: {directory}")

        json_files = path.glob('*.json')
        count = 0

        for json_file in json_files:
            try:
                self.load_roster(str(json_file))
                count += 1
            except (ValueError, FileNotFoundError) as e:
                logger.warning(f"Skipping invalid roster {json_file.name}: {e}")

        logger.info(f"Loaded {count} rosters from {directory}")

    def get_player_name(self, team_name: str, team_year: int, jersey_number: str) -> Optional[str]:
        """
        Look up player name by team, year, and jersey.

        Args:
            team_name: Team name
            team_year: Team year
            jersey_number: Jersey number (as string)

        Returns:
            Player name or None if not found
        """
        if team_name not in self.rosters:
            return None

        if team_year not in self.rosters[team_name]:
            return None

        return self.rosters[team_name][team_year].get(str(jersey_number))

    def get_all_teams(self) -> list:
        """Get list of all teams in rosters."""
        return list(self.rosters.keys())

    def get_team_years(self, team_name: str) -> list:
        """Get all years available for a team."""
        if team_name not in self.rosters:
            return []
        return sorted(self.rosters[team_name].keys())
