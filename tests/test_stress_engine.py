"""Unit tests for StressEngine.

Tests covering configuration, stats tracking, pure utility functions,
and stateful logic like proxy rotation and rate limiting.
"""
import asyncio
from unittest.mock import patch

import pytest

from core.models import ProxyConfig
from core.stress_engine import (
    USER_AGENTS,
    AttackType,
    RequestMethod,
    StressConfig,
    StressEngine,
    StressStats,
)


def build_proxy_list(count=3):
    """Helper to build a list of ProxyConfig objects."""
    return [
        ProxyConfig(host=f"192.168.1.{i}", port=8080, protocol="http")
        for i in range(1, count + 1)
    ]


class TestDataClasses:
    """Tests for config and stats data classes."""

    def test_stress_config_defaults(self):
        """Test StressConfig default values."""
        config = StressConfig(target_url="http://example.com")
        assert config.target_url == "http://example.com"
        assert config.attack_type == AttackType.HTTP_FLOOD
        assert config.method == RequestMethod.GET
        assert config.threads == 100
        assert config.duration_seconds == 60
        assert config.rps_limit == 0
        assert config.randomize_user_agent is True

    def test_stress_config_custom_values(self):
        """Test StressConfig with custom values."""
        config = StressConfig(
            target_url="http://test.com",
            attack_type=AttackType.SLOWLORIS,
            method=RequestMethod.POST,
            threads=50
        )
        assert config.attack_type == AttackType.SLOWLORIS
        assert config.method == RequestMethod.POST
        assert config.threads == 50

    def test_stress_stats_initialization(self):
        """Test StressStats initialization values."""
        stats = StressStats()
        assert stats.requests_sent == 0
        assert stats.requests_success == 0
        assert stats.requests_failed == 0
        assert stats.min_latency_ms == float('inf')
        assert stats.max_latency_ms == 0.0
        assert isinstance(stats.response_codes, dict)
        assert isinstance(stats.error_types, dict)

    def test_attack_type_enum(self):
        """Test AttackType enum values."""
        assert AttackType.HTTP_FLOOD.value == "http_flood"
        assert AttackType.SLOWLORIS.value == "slowloris"
        assert AttackType.RUDY.value == "rudy"
        assert AttackType.RANDOMIZED.value == "randomized"

    def test_request_method_enum(self):
        """Test RequestMethod enum values."""
        assert RequestMethod.GET.value == "GET"
        assert RequestMethod.POST.value == "POST"


class TestStressEnginePureFunctions:
    """Tests for pure functions in StressEngine."""

    def setup_method(self):
        self.config = StressConfig(target_url="http://example.com")
        self.proxies = build_proxy_list(1)
        self.engine = StressEngine(self.config, self.proxies)

    def test_get_random_payload(self):
        """Test random payload generation."""
        size = 128
        payload = self.engine._get_random_payload(size)
        assert len(payload) == size
        assert isinstance(payload, str)
        # Check it contains only expected chars
        import string
        allowed = string.ascii_letters + string.digits
        assert all(c in allowed for c in payload)

    def test_get_random_payload_empty(self):
        """Test zero-length payload."""
        payload = self.engine._get_random_payload(0)
        assert payload == ""

    def test_get_headers_default(self):
        """Test default headers generation."""
        headers = self.engine._get_headers()
        assert "Accept" in headers
        assert "User-Agent" in headers
        assert "Connection" in headers
        assert headers["Connection"] == "keep-alive"

    def test_get_headers_random_ua(self):
        """Test User-Agent randomization."""
        # This is probabilistic, but with enough samples we should see variance
        uas = set()
        for _ in range(20):
            headers = self.engine._get_headers()
            uas.add(headers["User-Agent"])

        # Should have picked at least 2 different UAs from the list
        assert len(uas) > 1
        assert all(ua in USER_AGENTS for ua in uas)

    def test_get_headers_static_ua(self):
        """Test static User-Agent when randomization disabled."""
        self.engine.config.randomize_user_agent = False
        headers1 = self.engine._get_headers()
        headers2 = self.engine._get_headers()
        assert headers1["User-Agent"] == headers2["User-Agent"]
        assert headers1["User-Agent"] == USER_AGENTS[0]

    def test_get_headers_custom(self):
        """Test custom headers are included."""
        self.engine.config.custom_headers = {"X-Test": "123", "Authorization": "Bearer token"}
        headers = self.engine._get_headers()
        assert headers["X-Test"] == "123"
        assert headers["Authorization"] == "Bearer token"

    def test_calculate_rps(self):
        """Test RPS calculation."""
        self.engine.stats.elapsed_seconds = 10.0
        self.engine.stats.requests_sent = 100
        self.engine._calculate_rps()
        assert self.engine.stats.current_rps == 10.0

    def test_calculate_rps_zero_time(self):
        """Test RPS calculation with zero elapsed time (no division by zero)."""
        self.engine.stats.elapsed_seconds = 0.0
        self.engine.stats.requests_sent = 100
        self.engine._calculate_rps()
        # Should remain 0.0 or unchanged, but definitely no crash
        assert self.engine.stats.current_rps == 0.0


class TestStressEngineStateful:
    """Tests for stateful logic (Proxies, Stats, Rate Limit)."""

    def setup_method(self):
        self.config = StressConfig(target_url="http://example.com")
        self.proxies = build_proxy_list(3)
        self.engine = StressEngine(self.config, self.proxies)

    @pytest.mark.asyncio
    async def test_get_next_proxy_round_robin(self):
        """Test round-robin proxy rotation."""
        p1 = await self.engine._get_next_proxy()
        p2 = await self.engine._get_next_proxy()
        p3 = await self.engine._get_next_proxy()
        p4 = await self.engine._get_next_proxy()

        assert p1.host == "192.168.1.1"
        assert p2.host == "192.168.1.2"
        assert p3.host == "192.168.1.3"
        assert p4.host == "192.168.1.1"  # Loop back to start

    @pytest.mark.asyncio
    async def test_get_next_proxy_empty_list(self):
        """Test behavior with empty proxy list."""
        engine = StressEngine(self.config, [])
        proxy = await engine._get_next_proxy()
        assert proxy is None

    @pytest.mark.asyncio
    async def test_get_next_proxy_filters_non_http(self):
        """Test that init filters out non-HTTP proxies."""
        mixed_proxies = [
            ProxyConfig(host="1.1.1.1", port=80, protocol="http"),
            ProxyConfig(host="2.2.2.2", port=1080, protocol="socks5"),
        ]
        engine = StressEngine(self.config, mixed_proxies)

        # Should only have the HTTP proxy
        assert len(engine.proxies) == 1
        p1 = await engine._get_next_proxy()
        assert p1.host == "1.1.1.1"

    @pytest.mark.asyncio
    async def test_get_next_proxy_tracks_usage(self):
        """Test that used proxies are tracked in _used_proxies set."""
        await self.engine._get_next_proxy()
        assert len(self.engine._used_proxies) == 1

        # Using same proxy again shouldn't increase set size if key is same
        # But here we rotate through 3 unique ones
        await self.engine._get_next_proxy()
        assert len(self.engine._used_proxies) == 2

    @pytest.mark.asyncio
    async def test_should_rate_limit_unlimited(self):
        """Test rate limiting returns False when unlimited."""
        self.engine.config.rps_limit = 0
        should_limit = await self.engine._should_rate_limit()
        assert should_limit is False

    @pytest.mark.asyncio
    async def test_should_rate_limit_exceeds(self):
        """Test rate limiting returns True when exceeded."""
        self.engine.config.rps_limit = 5

        # Fill up the quota
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            for _ in range(5):
                should_limit = await self.engine._should_rate_limit()
                assert should_limit is False

            # Next one should be limited
            should_limit = await self.engine._should_rate_limit()
            assert should_limit is True

    @pytest.mark.asyncio
    async def test_should_rate_limit_clears_old(self):
        """Test that old request timestamps are cleared."""
        self.engine.config.rps_limit = 5

        # Add requests at t=1000
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            for _ in range(5):
                await self.engine._should_rate_limit()

        # Move time to t=1002 (older requests should expire)
        with patch("time.time") as mock_time:
            mock_time.return_value = 1002.0
            # Should be able to request again
            should_limit = await self.engine._should_rate_limit()
            assert should_limit is False
            # Internal list should only have the new one
            assert len(self.engine._request_times) == 1

    @pytest.mark.asyncio
    async def test_update_stats_success(self):
        """Test updating stats for successful request."""
        await self.engine._update_stats(
            success=True,
            latency_ms=150.0,
            bytes_sent=100,
            bytes_received=500,
            status_code=200
        )

        assert self.engine.stats.requests_sent == 1
        assert self.engine.stats.requests_success == 1
        assert self.engine.stats.requests_failed == 0
        assert self.engine.stats.bytes_sent == 100
        assert self.engine.stats.bytes_received == 500
        assert self.engine.stats.response_codes[200] == 1
        assert self.engine.stats.avg_latency_ms == 150.0

    @pytest.mark.asyncio
    async def test_update_stats_failure(self):
        """Test updating stats for failed request."""
        await self.engine._update_stats(
            success=False,
            error_type="timeout",
            proxy_failed=True
        )

        assert self.engine.stats.requests_sent == 1
        assert self.engine.stats.requests_success == 0
        assert self.engine.stats.requests_failed == 1
        assert self.engine.stats.error_types["timeout"] == 1
        assert self.engine.stats.proxies_failed == 1

    @pytest.mark.asyncio
    async def test_update_stats_latency_calculation(self):
        """Test min/max/avg latency calculations."""
        # First request: 100ms
        await self.engine._update_stats(success=True, latency_ms=100.0)
        assert self.engine.stats.min_latency_ms == 100.0
        assert self.engine.stats.max_latency_ms == 100.0
        assert self.engine.stats.avg_latency_ms == 100.0

        # Second request: 200ms
        await self.engine._update_stats(success=True, latency_ms=200.0)
        assert self.engine.stats.min_latency_ms == 100.0
        assert self.engine.stats.max_latency_ms == 200.0
        assert self.engine.stats.avg_latency_ms == 150.0

        # Third request: 50ms
        await self.engine._update_stats(success=True, latency_ms=50.0)
        assert self.engine.stats.min_latency_ms == 50.0

    @pytest.mark.asyncio
    async def test_update_stats_rolling_average(self):
        """Test that average latency uses rolling window."""
        # Directly manipulate latencies to fill buffer
        # This implementation detail test assumes `_latencies` is used
        # We want to make sure it doesn't grow indefinitely

        # Fill with 1000 items
        self.engine._latencies = [100.0] * 1000

        # Add one more
        await self.engine._update_stats(success=True, latency_ms=200.0)

        assert len(self.engine._latencies) == 1000
        # The last one should be 200.0
        assert self.engine._latencies[-1] == 200.0

    @pytest.mark.asyncio
    async def test_update_stats_concurrency(self):
        """Test thread safety of stats updates."""
        # Create multiple concurrent updates
        tasks = []
        for _ in range(100):
            tasks.append(self.engine._update_stats(success=True, latency_ms=10))

        await asyncio.gather(*tasks)

        assert self.engine.stats.requests_sent == 100
        assert self.engine.stats.requests_success == 100


class TestStressEngineControl:
    """Tests for engine control methods (start, stop, pause)."""

    def setup_method(self):
        self.config = StressConfig(target_url="http://example.com")
        self.proxies = build_proxy_list(1)
        self.engine = StressEngine(self.config, self.proxies)

    def test_stop_sets_flags(self):
        """Test stop method sets running flag and events."""
        self.engine._running = True
        self.engine.stop()
        assert self.engine.is_running is False
        assert self.engine._stop_event.is_set()

    def test_pause_resume_flags(self):
        """Test pause and resume methods."""
        self.engine.pause()
        assert self.engine.is_paused is True
        assert not self.engine._pause_event.is_set()

        self.engine.resume()
        assert self.engine.is_paused is False
        assert self.engine._pause_event.is_set()
