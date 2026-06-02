"""Test that conftest fixtures are properly defined."""

import pytest


def test_app_fixture_exists(app):
    """Verify app fixture creates a Flask application."""
    assert app is not None
    assert hasattr(app, 'db')


def test_client_fixture_exists(client):
    """Verify client fixture creates a Flask test client."""
    assert client is not None
    # Test client should be able to make requests
    response = client.get('/health')
    assert response.status_code == 200


def test_db_fixture_exists(db):
    """Verify db fixture creates a Database instance."""
    assert db is not None
    assert hasattr(db, 'conn')
    assert hasattr(db, '_lock')
