"""Shared utilities for face detection and jersey number recognition."""

import logging
import os
from typing import List, Dict, Optional
import cv2
import numpy as np

logger = logging.getLogger(__name__)


def load_image(photo_path: str) -> Optional[np.ndarray]:
    """
    Load an image from disk and return as BGR numpy array.

    Args:
        photo_path: Absolute path to image file

    Returns:
        np.ndarray in BGR format, or None if file not found/unreadable
    """
    if not photo_path or not os.path.exists(photo_path):
        logger.warning(f"Image not found: {photo_path}")
        return None

    try:
        img = cv2.imread(photo_path)
        if img is None:
            logger.warning(f"Failed to read image: {photo_path}")
            return None
        return img
    except Exception as e:
        logger.error(f"Error loading image {photo_path}: {e}")
        return None


def get_game_context(db) -> List[Dict]:
    """
    Retrieve the active game context from the database.

    Args:
        db: Database instance (current_app.db in Flask endpoints)

    Returns:
        List of dicts with keys: team_name, team_year, uniform_color
        Empty list if no context is set
    """
    try:
        return db.context.get_game_context()
    except Exception as e:
        logger.error(f"Error getting game context: {e}")
        return []


def match_to_roster(
    db,
    jersey_number: str,
    value_type: str = "jersey_number",
    team_name: Optional[str] = None,
    jersey_color: Optional[str] = None,
    year: Optional[int] = None,
) -> Optional[Dict]:
    """
    Match a detected value (jersey number) to a roster entry.

    When value_type is 'jersey_number', requires:
    - jersey_number: the detected number
    - team_name: the team playing (from game context)
    - jersey_color: the detected uniform color (from game context)
    - year: the tournament year (from game context)

    Returns a roster entry dict if unique match found, None otherwise.

    Args:
        db: Database instance
        jersey_number: The detected jersey number (string, e.g. "31")
        value_type: Type of detection ("jersey_number" is currently supported)
        team_name: Team name (from game context)
        jersey_color: Uniform color (from game context)
        year: Tournament year (from game context)

    Returns:
        Dict with roster entry (id, team_name, team_year, jersey_number, player_name, uniform_color)
        or None if no match
    """
    if value_type != "jersey_number":
        logger.warning(f"Unknown value_type: {value_type}")
        return None

    if not jersey_number or not team_name or not jersey_color or not year:
        logger.debug(f"Incomplete matching criteria: jersey={jersey_number}, team={team_name}, color={jersey_color}, year={year}")
        return None

    try:
        # Use roster repository's find method to locate a matching entry
        # with all four criteria: jersey_number, team_name, uniform_color, year
        entry = db.roster.find_by_jersey_color_and_team(
            jersey_number=jersey_number,
            team_name=team_name,
            jersey_color=jersey_color,
            year=year,
        )
        return entry
    except Exception as e:
        logger.error(f"Error matching to roster: {e}")
        return None


def normalize_jersey_number(text: str) -> Optional[str]:
    """
    Normalize detected text to a jersey number.

    Extract leading digits from text, return as string.
    E.g. "31" or "3" from "31 DE Morgan" or "031"

    Args:
        text: Raw OCR text

    Returns:
        Normalized jersey number (e.g. "31") or None if no digits found
    """
    if not text:
        return None

    # Extract leading digits
    digits = ""
    for char in text.strip():
        if char.isdigit():
            digits += char
        else:
            break

    return digits if digits else None
