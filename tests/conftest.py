"""Shared pytest fixtures for all tests."""

import os
import tempfile
from pathlib import Path

import pytest
from src.api import create_app
from src.db import Database


def pytest_configure(config):
    """Ensure Tesseract uses a project-local, readable temp dir.

    pytesseract round-trips images through $TMPDIR.  On some systems
    (macOS sandbox envs) Leptonica cannot open files in /tmp/… or
    /var/folders/…, making every OCR call fail silently.  Pointing
    TMPDIR at .ocr_tmp in the project root fixes this before any test
    imports pytesseract or jersey_recognition.
    """
    project_root = Path(__file__).resolve().parent.parent
    ocr_tmp = project_root / ".ocr_tmp"
    ocr_tmp.mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = str(ocr_tmp)
    tempfile.tempdir = str(ocr_tmp)


@pytest.fixture
def app():
    """Create a Flask test app with in-memory database."""
    app = create_app(db_path=":memory:")
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()


@pytest.fixture
def db():
    """Create an in-memory SQLite database for testing."""
    db = Database(":memory:")
    db.init_schema()
    yield db
    db.close()
