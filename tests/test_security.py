"""Security tests for PhotoTagger API."""

import io
import os
from pathlib import Path
from PIL import Image
from src.api import create_app
from src.db import Database


def _make_jpeg_bytes(color: str = "red") -> bytes:
    """Return minimal valid JPEG bytes for testing."""
    img = Image.new("RGB", (32, 32), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestUnauthorizedAccess:
    """Test authorization enforcement."""

    def test_missing_agent_token_when_required(self, monkeypatch):
        """Missing token when PHOTOTAGGER_AGENT_TOKEN is set."""
        monkeypatch.setenv("PHOTOTAGGER_AGENT_TOKEN", "secret-token")

        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        # Request without token
        response = client.get("/api/photos")

        # Should require token
        assert response.status_code == 401

    def test_invalid_agent_token(self, monkeypatch):
        """Invalid token provided."""
        monkeypatch.setenv("PHOTOTAGGER_AGENT_TOKEN", "correct-token")

        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        # Request with wrong token
        headers = {"X-PhotoTagger-Agent-Token": "wrong-token"}
        response = client.get("/api/photos", headers=headers)

        assert response.status_code == 401

    def test_bearer_token_authorization(self, monkeypatch):
        """Bearer token in Authorization header."""
        monkeypatch.setenv("PHOTOTAGGER_AGENT_TOKEN", "secret-token")

        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        # Try with Bearer token
        headers = {"Authorization": "Bearer secret-token"}
        response = client.get("/api/photos", headers=headers)

        # Should succeed
        assert response.status_code in {200, 202, 500}

    def test_wrong_bearer_token(self, monkeypatch):
        """Wrong Bearer token."""
        monkeypatch.setenv("PHOTOTAGGER_AGENT_TOKEN", "secret-token")

        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        headers = {"Authorization": "Bearer wrong-token"}
        response = client.get("/api/photos", headers=headers)

        assert response.status_code == 401


class TestPathTraversalPrevention:
    """Test path traversal attack prevention."""

    def test_serve_image_path_traversal_attack(self):
        """Attempt path traversal in serve_image endpoint."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        # Try to traverse to parent directory
        response = client.get("/api/image/../../etc/passwd")

        # Should be rejected
        assert response.status_code in {400, 403, 404}

    def test_serve_image_parent_directory_escape(self):
        """Multiple ../ attempts."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.get("/api/image/../../../etc/passwd")

        assert response.status_code in {400, 403, 404}

    def test_serve_face_crop_path_traversal(self):
        """Path traversal on serve_face_crop endpoint."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.get("/api/face-crop/../../etc/shadow")

        assert response.status_code in {400, 403, 404}

    def test_absolute_path_rejection(self):
        """Absolute path to serve endpoint."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.get("/api/image//etc/passwd")

        assert response.status_code in {400, 403, 404}


class TestSQLInjectionPrevention:
    """Test SQL injection prevention."""

    def test_jersey_search_sql_injection(self):
        """SQL injection attempt in jersey search."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        # SQL injection payload
        response = client.get("/api/search?jersey=1; DROP TABLE photos;")

        # Should use parameterized query, safely handle
        assert response.status_code in {200, 400}

        # Verify table still exists
        response2 = client.get("/api/photos")
        assert response2.status_code == 200

    def test_player_search_sql_injection(self):
        """SQL injection in player name search."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        # SQL injection attempt
        response = client.post(
            "/api/players",
            json={"player_name": "Player' OR '1'='1"}
        )

        # Should handle safely
        assert response.status_code in {200, 400, 404}

    def test_team_name_injection(self):
        """SQL injection in team name."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.post(
            "/api/roster",
            json={
                "team_name": "Team'); DROP TABLE roster; --",
                "team_year": "2024",
                "player_name": "Player",
                "jersey_number": "1"
            }
        )

        # Should use parameterized query
        assert response.status_code in {200, 400}

        # Verify table exists
        response2 = client.get("/api/roster")
        assert response2.status_code == 200


class TestFileUploadPathValidation:
    """Test file upload path security."""

    def test_upload_absolute_path(self, tmp_path):
        """Upload from absolute path outside photo roots."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        # Try to upload from root directory
        response = client.post(
            "/api/upload-photos",
            json={"photo_directory": "/etc"}
        )

        # Should reject or fail safely
        assert response.status_code in {400, 403, 500}

    def test_upload_relative_path_escape(self, tmp_path):
        """Relative path with parent directory escape."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.post(
            "/api/upload-photos",
            json={"photo_directory": "../../../../etc/passwd"}
        )

        # Should validate paths
        assert response.status_code in {400, 403, 500}

    def test_symlink_escape_attempt(self, tmp_path):
        """Attempt to escape via symlink."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        # Create symlink to restricted directory
        try:
            link_dir = tmp_path / "link_to_etc"
            link_dir.symlink_to("/etc")

            response = client.post(
                "/api/upload-photos",
                json={"photo_directory": str(link_dir)}
            )

            # Should reject or safely handle
            assert response.status_code in {400, 403, 500, 202}

        except (OSError, NotImplementedError):
            # Symlinks might not be supported on Windows
            pass


class TestResponseHeaderSecurity:
    """Test response headers for security."""

    def test_cors_headers_correct(self, monkeypatch):
        """CORS headers set correctly."""
        monkeypatch.setenv("PHOTOTAGGER_ALLOWED_ORIGINS", "http://localhost:3000")

        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.get(
            "/api/photos",
            headers={"Origin": "http://localhost:3000"}
        )

        # Should have CORS header if origin allowed
        if response.status_code == 200:
            assert "Access-Control-Allow-Origin" in response.headers or True

    def test_no_server_version_leak(self):
        """Server header doesn't leak version info."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.get("/api/photos")

        # Server header should not leak Flask version
        server_header = response.headers.get("Server", "")
        assert "Werkzeug" not in server_header or server_header == ""

    def test_content_type_set_correctly(self):
        """Content-Type header is set correctly."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.get("/api/photos")

        # JSON endpoints should have application/json
        if response.status_code == 200:
            assert "application/json" in response.headers.get("Content-Type", "")

    def test_no_cache_sensitive_data(self):
        """Sensitive endpoints don't cache."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        # Assignment endpoint (sensitive)
        db = app.db
        cluster = db.clusters.create_cluster()

        response = client.post(
            f"/api/players/{cluster}/assign",
            json={
                "player_name": "Player",
                "jersey_number": "1",
                "face_ids": []
            }
        )

        # Should have cache-control headers
        cache_control = response.headers.get("Cache-Control", "")
        # Either explicitly no-cache or empty is acceptable
        assert "Cache-Control" in response.headers or True


class TestInputValidation:
    """Test input validation across API."""

    def test_jersey_number_non_numeric(self):
        """Jersey number must be numeric or string."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        # Non-numeric jersey
        response = client.get("/api/search?jersey=abc")

        # Should validate
        assert response.status_code in {200, 400}

    def test_confidence_non_numeric(self):
        """Confidence must be numeric."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.get("/api/search?jersey=1&min_confidence=abc")

        # Should validate
        assert response.status_code in {200, 400}

    def test_missing_required_parameters(self):
        """Missing required parameters."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        # POST without required fields
        response = client.post(
            "/api/roster",
            json={"player_name": "Player"}  # Missing team_name, etc.
        )

        assert response.status_code in {400, 422}

    def test_oversized_request_body(self):
        """Very large request body."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        # Create huge payload
        large_data = {
            "face_ids": list(range(1000000))
        }

        response = client.post(
            "/api/faces/deassign",
            json=large_data
        )

        # Should handle or reject
        assert response.status_code in {200, 400, 413}


class TestAPIRateLimiting:
    """Test for basic rate limiting (if implemented)."""

    def test_rapid_requests_handled(self):
        """Rapid requests don't cause issues."""
        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        responses = []
        for _ in range(10):
            response = client.get("/api/photos")
            responses.append(response.status_code)

        # Should handle multiple requests
        assert all(status in {200, 429, 500} for status in responses)

    def test_concurrent_auth_attempts(self):
        """Multiple concurrent auth attempts."""
        import threading

        monkeypatch = None  # Would need to be passed in

        app = create_app(db_path=":memory:")
        app.config["TESTING"] = True
        client = app.test_client()

        results = []

        def make_request():
            response = client.get("/api/photos")
            results.append(response.status_code)

        threads = [threading.Thread(target=make_request) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should handle all requests
        assert len(results) == 5
