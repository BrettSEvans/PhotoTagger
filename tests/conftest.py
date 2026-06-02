"""Shared pytest fixtures for all tests."""

import pytest
from src.api import create_app
from src.db import Database


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
