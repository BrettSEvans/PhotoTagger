"""Security tests for SSRF and path traversal fixes."""
import pytest
from src.roster_import import RosterImporter, RosterImportError


class TestSSRFValidation:
    """Test URL validation to prevent SSRF attacks."""

    def test_reject_localhost_by_hostname(self):
        """Reject localhost by hostname."""
        with pytest.raises(RosterImportError, match="localhost are not allowed"):
            RosterImporter.fetch_url("http://localhost:8080/roster.csv")

    def test_reject_localhost_by_ip(self):
        """Reject localhost by IP address."""
        with pytest.raises(RosterImportError, match="localhost are not allowed"):
            RosterImporter.fetch_url("http://127.0.0.1:8080/roster.csv")

    def test_reject_ipv6_loopback(self):
        """Reject IPv6 loopback."""
        with pytest.raises(RosterImportError, match="localhost are not allowed"):
            RosterImporter.fetch_url("http://[::1]/roster.csv")

    def test_reject_private_ip_192(self):
        """Reject private IP 192.168.x.x."""
        with pytest.raises(RosterImportError, match="private or reserved"):
            RosterImporter.fetch_url("http://192.168.1.1/roster.csv")

    def test_reject_private_ip_10(self):
        """Reject private IP 10.x.x.x."""
        with pytest.raises(RosterImportError, match="private or reserved"):
            RosterImporter.fetch_url("http://10.0.0.1/roster.csv")

    def test_reject_aws_metadata(self):
        """Reject AWS metadata service."""
        with pytest.raises(RosterImportError, match="metadata services"):
            RosterImporter.fetch_url("http://169.254.169.254/latest/meta-data/")

    def test_reject_gcp_metadata(self):
        """Reject GCP metadata service."""
        with pytest.raises(RosterImportError, match="metadata services"):
            RosterImporter.fetch_url("http://metadata.google.internal/computeMetadata/")

    def test_reject_azure_metadata(self):
        """Reject Azure metadata service."""
        with pytest.raises(RosterImportError, match="metadata services"):
            RosterImporter.fetch_url("http://169.254.170.2/metadata/")

    def test_reject_ftp_protocol(self):
        """Reject non-HTTP protocols."""
        with pytest.raises(RosterImportError, match="HTTP/HTTPS"):
            RosterImporter.fetch_url("ftp://example.com/roster.csv")

    def test_reject_file_protocol(self):
        """Reject file:// protocol."""
        with pytest.raises(RosterImportError, match="HTTP/HTTPS"):
            RosterImporter.fetch_url("file:///etc/passwd")

    def test_reject_missing_hostname(self):
        """Reject URLs with missing hostname."""
        with pytest.raises(RosterImportError, match="missing hostname"):
            RosterImporter.fetch_url("http:///roster.csv")

    def test_allow_valid_https_url(self):
        """Valid HTTPS URLs should pass validation (will fail on network)."""
        # This will fail because we can't actually fetch, but it should
        # pass the validation and fail on the network request instead
        with pytest.raises(RosterImportError, match="Could not fetch"):
            RosterImporter.fetch_url("https://example.com/roster.csv")

    def test_allow_valid_http_url(self):
        """Valid HTTP URLs should pass validation (will fail on network)."""
        with pytest.raises(RosterImportError, match="Could not fetch"):
            RosterImporter.fetch_url("http://example.com/roster.csv")
