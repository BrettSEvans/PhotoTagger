import logging
import os
from datetime import datetime
from pathlib import Path

def setup_logging(level=logging.INFO):
    """Configure logging for CLI and scripts."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

def format_size(bytes_size: int) -> str:
    """Format byte size to human-readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f} TB"


# Photo path validation and parsing helpers for Flask routes

def parse_float(value) -> float | None:
    """Parse a value as a float, returning None if conversion fails."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_int_arg(value) -> int | None:
    """Parse a value as an integer, returning None if conversion fails."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def configured_photo_roots() -> list[Path]:
    """Return list of allowed photo root directories from environment."""
    raw = os.environ.get("PHOTOTAGGER_ALLOWED_PHOTO_ROOTS", "").strip()
    if not raw:
        return []
    parts = [part.strip() for chunk in raw.split(os.pathsep) for part in chunk.split(",")]
    return [Path(part).expanduser().resolve() for part in parts if part]


def is_allowed_photo_path(photo_path: str) -> bool:
    """Check if a photo path is within allowed roots."""
    path = Path(photo_path).expanduser().resolve()
    if ".git" in path.parts:
        # Prevent XMP sidecar writes into git object files if a photo root overlaps
        # with a repo directory (e.g. someone pointed the app at ~/Code by mistake).
        return False
    roots = configured_photo_roots()
    if not roots:
        # No allowlist configured: permit all paths (local single-user mode).
        return True
    return any(path == root or root in path.parents for root in roots)


def is_allowed_photo_directory(photo_dir: str) -> bool:
    """Check if a directory is within allowed roots (alias for is_allowed_photo_path)."""
    return is_allowed_photo_path(photo_dir)
