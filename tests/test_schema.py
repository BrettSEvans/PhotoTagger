"""Test schema initialization module."""

import sqlite3
import tempfile
from pathlib import Path

from src.schema import init_schema


def test_init_schema_creates_all_tables():
    """Verify init_schema creates all 8 required tables."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        init_schema(conn)

        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = {row[0] for row in cursor.fetchall()}

        expected_tables = {
            'game_context_teams',
            'photo_batches',
            'photos',
            'ocr_results',
            'faces',
            'rosters',
            'player_clusters',
            'processing_jobs',
        }
        assert tables == expected_tables, f"Expected {expected_tables}, got {tables}"
        conn.close()


def test_init_schema_creates_photos_table_with_columns():
    """Verify init_schema creates photos table with expected columns."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))

        init_schema(conn)

        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(photos)")
        columns = {row[1] for row in cursor.fetchall()}

        expected_columns = {'id', 'file_path', 'file_hash', 'file_size', 'created_at', 'ingested_at', 'source_folder', 'batch_id'}
        assert expected_columns.issubset(columns), f"Missing columns: {expected_columns - columns}"
        conn.close()


def test_init_schema_idempotent():
    """Verify calling init_schema twice doesn't fail."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # First call
        init_schema(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM sqlite_master WHERE type='table'")
        first_count = cursor.fetchone()['cnt']

        # Second call (should not fail)
        init_schema(conn)
        cursor.execute("SELECT COUNT(*) as cnt FROM sqlite_master WHERE type='table'")
        second_count = cursor.fetchone()['cnt']

        assert first_count == second_count, "Schema should be idempotent"
        conn.close()
