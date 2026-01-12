"""
Unit tests for ThreadedProxyManager and GeoIP lookup functions.

Tests proxy scraping regex, GeoIP lookup chain, and result handling
without making actual network requests.
"""

from unittest.mock import MagicMock, patch

from core.models import ProxyConfig
from core.proxy_manager import (
    ThreadedProxyManager,
    _lookup_geoip_api,
    _lookup_geoip_local,
    lookup_geoip,
)
from tests.fixtures.mock_responses import (
    build_proxy_check_result,
    build_proxy_config,
)


class TestProxyRegex:
    """Tests for proxy extraction regex pattern."""

    def setup_method(self):
        self.manager = ThreadedProxyManager()

    def test_extract_basic_proxy(self):
        """Extract basic IP:PORT from text."""
        text = "Proxy: 192.168.1.1:8080"
        matches = self.manager.regex_pattern.findall(text)

        assert len(matches) == 1
        assert matches[0] == "192.168.1.1:8080"

    def test_extract_multiple_proxies(self):
        """Extract multiple proxies from text."""
        text = """
        192.168.1.1:8080
        10.0.0.1:3128
        172.16.0.1:1080
        """
        matches = self.manager.regex_pattern.findall(text)

        assert len(matches) == 3

    def test_extract_from_html(self):
        """Extract proxies from HTML content."""
        text = "<tr><td>192.168.1.1</td><td>8080</td></tr>"
        # Pattern looks for IP:PORT format, not separate cells
        matches = self.manager.regex_pattern.findall(text)

        # Won't match since IP and port are in separate elements
        assert len(matches) == 0

    def test_extract_inline_text(self):
        """Extract proxy from inline text."""
        text = "Use this proxy: 203.0.113.50:3128 for testing"
        matches = self.manager.regex_pattern.findall(text)

        assert len(matches) == 1
        assert matches[0] == "203.0.113.50:3128"

    def test_port_range_validation(self):
        """Port must be 2-5 digits."""
        # Valid ports
        valid = [
            "1.2.3.4:80",     # 2 digits
            "1.2.3.4:443",    # 3 digits
            "1.2.3.4:8080",   # 4 digits
            "1.2.3.4:65535",  # 5 digits
        ]
        for proxy in valid:
            matches = self.manager.regex_pattern.findall(proxy)
            assert len(matches) == 1, f"Should match: {proxy}"

        # Invalid ports (1 digit or 6+ digits)
        invalid = [
            "1.2.3.4:1",       # 1 digit
            "1.2.3.4:123456",  # 6 digits
        ]
        for proxy in invalid:
            matches = self.manager.regex_pattern.findall(proxy)
            assert len(matches) == 0, f"Should not match: {proxy}"


class TestGeoIPLocal:
    """Tests for local MaxMind database lookup."""

    @patch("core.proxy_manager._init_geoip_reader")
    def test_local_lookup_success(self, mock_init):
        """Successful local database lookup."""
        mock_reader = MagicMock()
        mock_response = MagicMock()
        mock_response.country.name = "Germany"
        mock_response.country.iso_code = "DE"
        mock_response.city.name = "Berlin"
        mock_reader.city.return_value = mock_response
        mock_init.return_value = mock_reader

        result = _lookup_geoip_local("5.6.7.8")

        assert result is not None
        assert result["country"] == "Germany"
        assert result["countryCode"] == "DE"
        assert result["city"] == "Berlin"

    @patch("core.proxy_manager._init_geoip_reader")
    def test_local_lookup_no_reader(self, mock_init):
        """No local database returns None."""
        mock_init.return_value = None

        result = _lookup_geoip_local("1.2.3.4")

        assert result is None

    @patch("core.proxy_manager._init_geoip_reader")
    def test_local_lookup_exception(self, mock_init):
        """Exception during lookup returns None."""
        mock_reader = MagicMock()
        mock_reader.city.side_effect = Exception("Address not in database")
        mock_init.return_value = mock_reader

        result = _lookup_geoip_local("0.0.0.0")

        assert result is None


class TestGeoIPApi:
    """Tests for GeoIP API fallback chain."""

    @patch("core.proxy_manager.std_requests.get")
    def test_api_lookup_success(self, mock_get):
        """First API returns valid response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "country": "France",
            "countryCode": "FR",
            "city": "Paris",
        }
        mock_get.return_value = mock_response

        result = _lookup_geoip_api("8.8.8.8")

        assert result is not None
        assert result["country"] == "France"

    @patch("core.proxy_manager.std_requests.get")
    def test_api_lookup_failure_tries_next(self, mock_get):
        """Failed API tries next in chain."""
        # First fails, second succeeds
        fail_response = MagicMock()
        fail_response.status_code = 429

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "country_name": "Japan",
            "country_code": "JP",
            "city": "Tokyo",
        }

        mock_get.side_effect = [fail_response, success_response]

        _lookup_geoip_api("1.1.1.1")

        assert mock_get.call_count >= 2

    @patch("core.proxy_manager.std_requests.get")
    def test_api_lookup_all_fail(self, mock_get):
        """All APIs fail returns Unknown fallback dict."""
        fail_response = MagicMock()
        fail_response.status_code = 500
        mock_get.return_value = fail_response

        result = _lookup_geoip_api("0.0.0.0")

        # Returns fallback dict with "Unknown" when all APIs fail
        assert result["country"] == "Unknown"


class TestGeoIPLookup:
    """Tests for combined GeoIP lookup with caching."""

    def setup_method(self):
        # Clear cache before each test
        import core.proxy_manager as pm
        pm._geoip_cache.clear()

    def test_cache_hit(self):
        """Cached results are returned immediately."""
        import core.proxy_manager as pm
        pm._geoip_cache["1.2.3.4"] = {
            "country": "Cached Country",
            "countryCode": "CC",
            "city": "Cached City",
        }

        result = lookup_geoip("1.2.3.4")

        assert result["country"] == "Cached Country"

    @patch("core.proxy_manager._lookup_geoip_local")
    @patch("core.proxy_manager._lookup_geoip_api")
    def test_local_first_then_api(self, mock_api, mock_local):
        """Tries local database before API."""
        mock_local.return_value = {
            "country": "Local Country",
            "countryCode": "LC",
            "city": "Local City",
        }

        result = lookup_geoip("5.6.7.8")

        mock_local.assert_called_once()
        mock_api.assert_not_called()
        assert result["country"] == "Local Country"

    @patch("core.proxy_manager._lookup_geoip_local")
    @patch("core.proxy_manager._lookup_geoip_api")
    def test_api_fallback_when_local_fails(self, mock_api, mock_local):
        """Falls back to API when local fails."""
        mock_local.return_value = None
        mock_api.return_value = {
            "country": "API Country",
            "countryCode": "AC",
            "city": "API City",
        }

        result = lookup_geoip("9.9.9.9")

        mock_local.assert_called_once()
        mock_api.assert_called_once()
        assert result["country"] == "API Country"

    @patch("core.proxy_manager._lookup_geoip_local")
    @patch("core.proxy_manager._lookup_geoip_api")
    def test_returns_none_when_all_fail(self, mock_api, mock_local):
        """Returns None when all lookups fail (callers handle this)."""
        mock_local.return_value = None
        mock_api.return_value = None

        result = lookup_geoip("0.0.0.0")

        # When both local and API return None, lookup_geoip returns None
        assert result is None


class TestProxyConfigCreation:
    """Tests for ProxyConfig and ProxyCheckResult creation."""

    def test_create_proxy_config(self):
        """Create ProxyConfig from factory."""
        proxy = build_proxy_config(
            host="192.168.1.1",
            port=8080,
            protocol="http"
        )

        assert isinstance(proxy, ProxyConfig)
        assert proxy.host == "192.168.1.1"
        assert proxy.port == 8080
        assert proxy.protocol == "http"

    def test_create_authenticated_proxy(self):
        """Create authenticated ProxyConfig."""
        proxy = build_proxy_config(
            host="192.168.1.1",
            port=8080,
            protocol="socks5",
            username="user",
            password="secret"
        )

        assert proxy.username == "user"
        assert proxy.password == "secret"

    def test_create_proxy_check_result(self):
        """Create ProxyCheckResult from factory."""
        result = build_proxy_check_result(
            host="1.2.3.4",
            port=8080,
            protocol="HTTP",
            status="Active",
            speed=150,
            country="United States",
            anonymity="Elite"
        )

        assert result.status == "Active"
        assert result.speed == 150
        assert result.anonymity == "Elite"
        assert result.proxy.host == "1.2.3.4"


class TestSpeedCalculation:
    """Tests for proxy speed/latency concepts."""

    def test_speed_from_elapsed_time(self):
        """Speed is calculated from response time in milliseconds."""
        elapsed_seconds = 0.250
        speed_ms = int(elapsed_seconds * 1000)

        assert speed_ms == 250

    def test_speed_rounding(self):
        """Speed is truncated to integer milliseconds."""
        elapsed_seconds = 0.1234
        speed_ms = int(elapsed_seconds * 1000)

        assert speed_ms == 123


class TestProxyProtocolDetection:
    """Tests for protocol detection from URLs and content."""

    def test_socks5_keyword_in_url(self):
        """SOCKS5 keyword indicates SOCKS5 protocol."""
        url = "https://example.com/socks5-proxies.txt"
        assert "socks5" in url.lower()

    def test_socks4_keyword_in_url(self):
        """SOCKS4 keyword indicates SOCKS4 protocol."""
        url = "https://example.com/proxies/socks4.txt"
        assert "socks4" in url.lower()

    def test_http_keyword_in_url(self):
        """HTTP keyword indicates HTTP protocol."""
        url = "https://example.com/http-proxies.txt"
        assert "http" in url.lower()


class TestProxyDeduplication:
    """Tests for proxy deduplication concepts."""

    def test_set_based_deduplication(self):
        """Same IP:PORT should deduplicate."""
        proxies = [
            ("192.168.1.1", 8080),
            ("192.168.1.1", 8080),  # Duplicate
            ("192.168.1.2", 8080),
        ]

        unique = set(proxies)

        assert len(unique) == 2

    def test_different_ports_kept(self):
        """Same IP with different ports are unique."""
        proxies = [
            ("192.168.1.1", 8080),
            ("192.168.1.1", 3128),
            ("192.168.1.1", 80),
        ]

        unique = set(proxies)

        assert len(unique) == 3


class TestProxyUrlFormatting:
    """Tests for proxy URL formatting concepts."""

    def test_http_proxy_format(self):
        """HTTP proxy URL format."""
        proxy = build_proxy_config(host="1.2.3.4", port=8080, protocol="http")
        url = f"{proxy.protocol}://{proxy.host}:{proxy.port}"

        assert url == "http://1.2.3.4:8080"

    def test_socks5_proxy_format(self):
        """SOCKS5 proxy URL format."""
        proxy = build_proxy_config(host="1.2.3.4", port=1080, protocol="socks5")
        url = f"{proxy.protocol}://{proxy.host}:{proxy.port}"

        assert url == "socks5://1.2.3.4:1080"

    def test_authenticated_proxy_format(self):
        """Authenticated proxy URL format."""
        proxy = build_proxy_config(
            host="1.2.3.4",
            port=8080,
            protocol="http",
            username="user",
            password="pass"
        )
        url = f"{proxy.protocol}://{proxy.username}:{proxy.password}@{proxy.host}:{proxy.port}"

        assert url == "http://user:pass@1.2.3.4:8080"
