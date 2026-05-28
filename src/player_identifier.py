import cv2
import numpy as np
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from src.player_detector import PlayerDetector
from src.uniform_detector import UniformDetector
from src.ocr import OCREngine
from src.roster import RosterManager
from src.db import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PlayerIdentifier:
    """Identify players using jersey number + uniform color + location."""

    def __init__(self, db: Database = None):
        """
        Initialize player identifier.

        Args:
            db: Database connection for OCR/roster storage
        """
        logger.info("Initializing PlayerIdentifier")
        self.db = db
        self.player_detector = PlayerDetector()
        self.uniform_detector = UniformDetector()
        self.ocr_engine = OCREngine(db) if db else None
        self.roster_manager = RosterManager()

    def identify_players_in_photo(
        self,
        image_path: str,
        roster_manager: RosterManager = None,
        team_year: int = 2026,
        min_confidence: float = 0.70
    ) -> Optional[List[Dict]]:
        """
        Identify all players in a photo using multi-factor matching.

        Process:
        1. Detect all faces in photo
        2. Filter to only on-field players
        3. For each player:
           - Extract jersey number (OCR)
           - Detect uniform color
           - Match to roster (jersey + color)

        Args:
            image_path: Path to photo
            roster_manager: Roster with team uniforms (if None, uses self.roster_manager)
            team_year: Year to search for in rosters
            min_confidence: Minimum combined confidence threshold (0.0-1.0)

        Returns:
            List of identified players:
            {
                'face_id': int,
                'jersey': '16',
                'shirt_color': 'red',
                'team': 'Team Alpha',
                'player_name': 'Edward Brown',
                'location': 'field',
                'jersey_confidence': 0.85,
                'color_confidence': 0.75,
                'match_confidence': 0.92,  # Combined
                'bbox': [x0, y0, x1, y1],
                'bbox_expanded': [x0, y0, x1, y1],
            }
        """
        if roster_manager is None:
            roster_manager = self.roster_manager

        try:
            path = Path(image_path)
            if not path.exists():
                logger.error(f"Image not found: {image_path}")
                return None

            logger.info(f"Identifying players in {path.name}")

            # Step 1: Detect all people
            all_people = self.player_detector.detect_players(str(image_path))
            if not all_people:
                logger.info("No people detected in photo")
                return []

            # Step 2: Filter to field players only
            field_players = self.player_detector.filter_field_players(all_people)
            if not field_players:
                logger.info("No field players detected (all appear to be spectators)")
                return []

            logger.info(f"Found {len(field_players)} potential field players")

            # Step 3: Identify each field player
            identified_players = []

            img = cv2.imread(str(image_path))
            if img is None:
                logger.error(f"Failed to read image: {image_path}")
                return None

            for person in field_players:
                # Extract jersey from expanded body region
                jersey, jersey_conf = self._extract_jersey(
                    img,
                    person['bbox_expanded']
                )

                if not jersey:
                    logger.debug(f"Face {person['face_id']}: No jersey detected")
                    continue

                # Detect uniform color from body region
                color_result = self._detect_color_from_region(
                    img,
                    person['bbox_expanded']
                )

                # Match to roster
                match = self._match_roster(
                    jersey=jersey,
                    shirt_color=color_result['color'],
                    roster_manager=roster_manager,
                    team_year=team_year
                )

                if match:
                    # Calculate combined confidence
                    combined_conf = self._calculate_combined_confidence(
                        jersey_conf,
                        color_result['confidence'],
                        match['match_score']
                    )

                    if combined_conf >= min_confidence:
                        identified_players.append({
                            'face_id': person['face_id'],
                            'jersey': jersey,
                            'shirt_color': color_result['color'],
                            'team': match['team_name'],
                            'player_name': match['player_name'],
                            'location': person['location'],
                            'jersey_confidence': jersey_conf,
                            'color_confidence': color_result['confidence'],
                            'match_confidence': match['match_score'],
                            'combined_confidence': combined_conf,
                            'bbox': person['bbox'],
                            'bbox_expanded': person['bbox_expanded'],
                        })

                        logger.info(
                            f"✓ Identified: Jersey {jersey} ({color_result['color']}) "
                            f"→ {match['player_name']} ({match['team_name']}) "
                            f"[{combined_conf:.1%}]"
                        )
                    else:
                        logger.debug(
                            f"Face {person['face_id']}: Low combined confidence "
                            f"({combined_conf:.1%} < {min_confidence:.1%})"
                        )
                else:
                    logger.debug(
                        f"Face {person['face_id']}: Jersey {jersey} + "
                        f"{color_result['color']} not found in roster"
                    )

            logger.info(f"Identified {len(identified_players)} players total")
            return identified_players

        except Exception as e:
            logger.error(f"Error identifying players in {image_path}: {e}")
            return None

    def _extract_jersey(
        self,
        img: np.ndarray,
        bbox: List[int]
    ) -> Tuple[Optional[str], float]:
        """
        Extract jersey number from player region.

        Args:
            img: Image array
            bbox: Expanded bounding box [x0, y0, x1, y1]

        Returns:
            (jersey_number_str, confidence)
        """
        if self.ocr_engine is None:
            logger.warning("OCR engine not available")
            return None, 0.0

        try:
            x0, y0, x1, y1 = bbox
            player_region = img[y0:y1, x0:x1]

            if player_region.size == 0:
                return None, 0.0

            # Run OCR on player region
            results = self.ocr_engine.reader.readtext(player_region)

            if not results:
                return None, 0.0

            # Extract text and confidence
            extracted_text = " ".join([text for (_, text, _) in results])
            avg_confidence = sum([conf for (_, _, conf) in results]) / len(results)

            # Extract jersey numbers from text
            jerseys = self.ocr_engine._extract_jerseys_from_text(extracted_text)

            if jerseys:
                # Return first (most prominent) jersey
                return jerseys[0], avg_confidence
            else:
                return None, 0.0

        except Exception as e:
            logger.warning(f"Error extracting jersey: {e}")
            return None, 0.0

    def _detect_color_from_region(self, img: np.ndarray, bbox: List[int]) -> Dict:
        """
        Detect uniform color from player region.

        Args:
            img: Image array
            bbox: Expanded bounding box [x0, y0, x1, y1]

        Returns:
            {
                'color': 'red' | 'white' | etc,
                'confidence': 0.0-1.0
            }
        """
        try:
            x0, y0, x1, y1 = bbox

            if y1 <= y0 or x1 <= x0:
                return {'color': 'unknown', 'confidence': 0.0}

            player_region = img[y0:y1, x0:x1]

            if player_region.size == 0:
                return {'color': 'unknown', 'confidence': 0.0}

            # Convert to HSV
            hsv = cv2.cvtColor(player_region, cv2.COLOR_BGR2HSV)

            # Analyze uniform color
            analysis = self.uniform_detector._analyze_region(hsv)

            # Match to color
            color, confidence = self.uniform_detector._match_color(analysis)

            return {'color': color, 'confidence': confidence}

        except Exception as e:
            logger.warning(f"Error detecting color: {e}")
            return {'color': 'unknown', 'confidence': 0.0}

    def _match_roster(
        self,
        jersey: str,
        shirt_color: str,
        roster_manager: RosterManager,
        team_year: int
    ) -> Optional[Dict]:
        """
        Match player to roster using jersey + color.

        Args:
            jersey: Jersey number string
            shirt_color: Detected uniform color
            roster_manager: RosterManager with team data
            team_year: Year to search for

        Returns:
            {
                'team_name': 'Team Alpha',
                'player_name': 'Edward Brown',
                'match_score': 0.85,  # Color match quality
            }
            or None if no match found
        """
        try:
            # Search across all teams
            best_match = None
            best_score = 0.0

            for team_name in roster_manager.get_all_teams():
                years = roster_manager.get_team_years(team_name)

                if team_year not in years:
                    continue

                team_data = roster_manager.rosters[team_name][team_year]

                # Check if jersey exists
                if jersey not in team_data.get('jerseys', {}):
                    continue

                # Check color match
                team_color = team_data.get('uniform_color', 'unknown')
                color_score = self._color_match_score(shirt_color, team_color)

                if color_score > best_score:
                    best_score = color_score
                    best_match = {
                        'team_name': team_name,
                        'player_name': team_data['jerseys'][jersey],
                        'match_score': color_score,
                    }

            return best_match

        except Exception as e:
            logger.warning(f"Error matching roster: {e}")
            return None

    def _color_match_score(self, detected: str, roster: str) -> float:
        """
        Score how well detected color matches roster color.

        Returns:
            0.0 (no match) to 1.0 (perfect match)
        """
        detected = detected.lower().strip()
        roster = roster.lower().strip()

        # Exact match
        if detected == roster:
            return 1.0

        # Color family matches
        color_families = {
            'red': ['red', 'crimson', 'dark red', 'maroon'],
            'white': ['white', 'light gray', 'off-white', 'cream'],
            'blue': ['blue', 'navy', 'royal blue', 'dark blue'],
            'black': ['black', 'dark gray', 'charcoal'],
            'yellow': ['yellow', 'gold', 'orange-yellow'],
            'green': ['green', 'dark green', 'forest green'],
        }

        detected_family = None
        roster_family = None

        for family, colors in color_families.items():
            if detected in colors:
                detected_family = family
            if roster in colors:
                roster_family = family

        # Family match
        if detected_family and roster_family and detected_family == roster_family:
            return 0.9  # High confidence but not perfect

        # No match
        return 0.0

    def _calculate_combined_confidence(
        self,
        jersey_conf: float,
        color_conf: float,
        match_score: float
    ) -> float:
        """
        Calculate combined confidence from three factors.

        Args:
            jersey_conf: Jersey number detection confidence (0-1)
            color_conf: Uniform color detection confidence (0-1)
            match_score: Roster match score (0-1)

        Returns:
            Combined confidence (0-1)
        """
        # Weight: jersey is most important (40%), color (35%), match (25%)
        combined = (
            jersey_conf * 0.40 +
            color_conf * 0.35 +
            match_score * 0.25
        )

        return min(combined, 1.0)
