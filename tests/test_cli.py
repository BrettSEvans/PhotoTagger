"""
Unit tests for src/cli.py.

Invokes CLI entry points programmatically by patching sys.argv and calling
the individual cmd_* functions with Namespace objects.  A real, temporary
SQLite DB is used for commands that read/write data.

NOTE: cmd_ocr is not tested here because OCREngine loads EasyOCR (very slow).
"""

import argparse
import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.cli import cmd_crawl, cmd_info, cmd_search, cmd_roster, main
from src.db import Database


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _temp_db(path: Path) -> str:
    """Create an initialised SQLite database and return its path string."""
    db = Database(str(path))
    db.init_schema()
    db.close()
    return str(path)


def _args(**kwargs):
    """Build a minimal argparse.Namespace from keyword arguments."""
    ns = argparse.Namespace()
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


# ---------------------------------------------------------------------------
# cmd_crawl
# ---------------------------------------------------------------------------

class TestCmdCrawl:
    """Tests for cli.cmd_crawl."""

    def test_crawl_nonexistent_dir_exits(self, tmp_path, capsys):
        db_path = _temp_db(tmp_path / "catalog.db")
        args = _args(photos=str(tmp_path / "nope"), db=db_path)
        with pytest.raises(SystemExit) as exc:
            cmd_crawl(args)
        assert exc.value.code == 1

    def test_crawl_empty_dir(self, tmp_path, capsys):
        photo_dir = tmp_path / "photos"
        photo_dir.mkdir()
        db_path = _temp_db(tmp_path / "catalog.db")
        args = _args(photos=str(photo_dir), db=db_path)
        cmd_crawl(args)
        captured = capsys.readouterr()
        assert "Crawling" in captured.out or "Found" in captured.out

    def test_crawl_with_jpeg(self, tmp_path, capsys):
        from PIL import Image
        photo_dir = tmp_path / "photos"
        photo_dir.mkdir()
        # Write a minimal JPEG
        img = Image.new("RGB", (32, 32), color=(200, 100, 50))
        img.save(str(photo_dir / "test.jpg"), format="JPEG")

        db_path = _temp_db(tmp_path / "catalog.db")
        args = _args(photos=str(photo_dir), db=db_path)
        cmd_crawl(args)
        captured = capsys.readouterr()
        assert "Ingested" in captured.out or "Found" in captured.out


# ---------------------------------------------------------------------------
# cmd_info
# ---------------------------------------------------------------------------

class TestCmdInfo:
    """Tests for cli.cmd_info."""

    def test_info_empty_db(self, tmp_path, capsys):
        db_path = _temp_db(tmp_path / "catalog.db")
        args = _args(db=db_path)
        cmd_info(args)
        captured = capsys.readouterr()
        assert "Database" in captured.out or "photos" in captured.out.lower()

    def test_info_shows_db_path(self, tmp_path, capsys):
        db_file = tmp_path / "mydb.db"
        db_path = _temp_db(db_file)
        args = _args(db=str(db_file))
        cmd_info(args)
        captured = capsys.readouterr()
        assert str(db_file) in captured.out

    def test_info_with_photos(self, tmp_path, capsys):
        """cmd_info shows file size total when photos exist (lines 166-167)."""
        from PIL import Image
        db_file = tmp_path / "catalog.db"
        db_path = _temp_db(db_file)
        # Add a photo to the DB
        photo = tmp_path / "test.jpg"
        Image.new("RGB", (32, 32)).save(str(photo))
        from src.db import Database
        db = Database(db_path)
        db.init_schema()
        db.photos.add_photo(str(photo), file_hash="infohash")
        db.close()
        args = _args(db=db_path)
        cmd_info(args)
        captured = capsys.readouterr()
        assert "1" in captured.out  # at least 1 photo shown


# ---------------------------------------------------------------------------
# cmd_search
# ---------------------------------------------------------------------------

class TestCmdSearch:
    """Tests for cli.cmd_search."""

    def test_search_returns_no_results(self, tmp_path, capsys):
        db_path = _temp_db(tmp_path / "catalog.db")
        args = _args(jersey="99", db=db_path)
        cmd_search(args)
        captured = capsys.readouterr()
        assert "No photos found" in captured.out or "Searching" in captured.out


# ---------------------------------------------------------------------------
# cmd_roster
# ---------------------------------------------------------------------------

class TestCmdRoster:
    """Tests for cli.cmd_roster."""

    def test_roster_list_empty_db(self, tmp_path, capsys):
        db_path = _temp_db(tmp_path / "catalog.db")
        args = _args(roster_command="list", db=db_path)
        cmd_roster(args)
        captured = capsys.readouterr()
        assert "No rosters" in captured.out or "Loaded rosters" in captured.out

    def test_roster_list_with_entries(self, tmp_path, capsys):
        """cmd_roster list shows entries when roster has data (lines 204-209)."""
        db_path = _temp_db(tmp_path / "catalog.db")
        # Insert a roster entry directly
        from src.db import Database
        db = Database(db_path)
        db.init_schema()
        db.roster.add_roster_entry("Team A", 2024, "7", "Alice")
        db.close()
        args = _args(roster_command="list", db=db_path)
        cmd_roster(args)
        captured = capsys.readouterr()
        assert "Team A" in captured.out or "roster" in captured.out.lower()

    def test_roster_load_nonexistent_file(self, tmp_path, capsys):
        db_path = _temp_db(tmp_path / "catalog.db")
        args = _args(
            roster_command="load",
            file=str(tmp_path / "nope.json"),
            db=db_path,
        )
        # Should print an error, not raise
        cmd_roster(args)
        captured = capsys.readouterr()
        assert "Error" in captured.out or "error" in captured.out.lower()

    def test_roster_load_valid_json(self, tmp_path, capsys):
        """cmd_roster load with valid JSON file (lines 179-190)."""
        import json
        db_path = _temp_db(tmp_path / "catalog.db")
        roster_file = tmp_path / "roster.json"
        roster_file.write_text(json.dumps({
            "team_name": "Team A",
            "team_year": 2024,
            "jerseys": {"7": "Alice Smith", "15": "Bob Jones"},
        }))
        args = _args(
            roster_command="load",
            file=str(roster_file),
            db=db_path,
        )
        cmd_roster(args)
        captured = capsys.readouterr()
        assert "Loaded" in captured.out or "saved" in captured.out.lower()


# ---------------------------------------------------------------------------
# main() / argument dispatch
# ---------------------------------------------------------------------------

class TestCmdOcr:
    """Tests for cli.cmd_ocr — mocked OCREngine to avoid loading EasyOCR."""

    def test_ocr_empty_db(self, tmp_path, capsys):
        db_path = _temp_db(tmp_path / "catalog.db")
        with patch("src.cli.OCREngine") as mock_engine:
            mock_engine.return_value.process_batch.return_value = {
                "photos_processed": 0, "jerseys_found": 0, "errors": 0
            }
            from src.cli import cmd_ocr
            args = _args(db=db_path, photo_id=None, parallel=False, workers=None)
            cmd_ocr(args)
        captured = capsys.readouterr()
        assert "Processed" in captured.out or "0" in captured.out

    def test_ocr_specific_photo_id(self, tmp_path, capsys):
        db_path = _temp_db(tmp_path / "catalog.db")
        with patch("src.cli.OCREngine") as mock_engine:
            mock_engine.return_value.process_batch.return_value = {
                "photos_processed": 1, "jerseys_found": 1, "errors": 0,
                "elapsed_time": 0.5,
            }
            from src.cli import cmd_ocr
            args = _args(db=db_path, photo_id=42, parallel=False, workers=None)
            cmd_ocr(args)
        captured = capsys.readouterr()
        assert "42" in captured.out or "Processing" in captured.out

    def test_ocr_parallel(self, tmp_path, capsys):
        db_path = _temp_db(tmp_path / "catalog.db")
        with patch("src.cli.OCREngine") as mock_engine:
            mock_engine.return_value.process_batch_parallel.return_value = {
                "photos_processed": 5, "jerseys_found": 3, "errors": 0,
                "elapsed_time": 1.2,
            }
            from src.cli import cmd_ocr
            args = _args(db=db_path, photo_id=None, parallel=True, workers=2)
            cmd_ocr(args)
        captured = capsys.readouterr()
        assert "parallel" in captured.out.lower() or "5" in captured.out


class TestMainDispatch:
    """Tests for the main() entry point argument dispatch."""

    def test_no_command_exits_1(self):
        with patch.object(sys, "argv", ["phototagger"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_unknown_command_exits_nonzero(self):
        with patch.object(sys, "argv", ["phototagger", "badcmd"]):
            with pytest.raises(SystemExit):
                main()

    def test_info_command_dispatched(self, tmp_path, capsys):
        db_path = _temp_db(tmp_path / "catalog.db")
        with patch.object(sys, "argv", ["phototagger", "info", "--db", db_path]):
            main()
        captured = capsys.readouterr()
        assert "Database" in captured.out or "photos" in captured.out.lower()

    def test_search_command_dispatched(self, tmp_path, capsys):
        db_path = _temp_db(tmp_path / "catalog.db")
        with patch.object(sys, "argv", ["phototagger", "search", "42", "--db", db_path]):
            main()
        captured = capsys.readouterr()
        assert "Searching" in captured.out or "No photos" in captured.out

    def test_roster_list_dispatched(self, tmp_path, capsys):
        db_path = _temp_db(tmp_path / "catalog.db")
        with patch.object(sys, "argv", ["phototagger", "roster", "list", "--db", db_path]):
            main()
        captured = capsys.readouterr()
        assert "roster" in captured.out.lower() or "No" in captured.out
