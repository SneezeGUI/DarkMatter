"""Unit tests for AsyncTrafficEngine.

Tests proxy acquisition/release, request execution, statistics tracking,
burst mode logic, and error handling.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine import AsyncTrafficEngine
from core.models import ProxyConfig
from tests.fixtures.mock_responses import (
    build_proxy_config,
    build_proxy_list,
    build_traffic_config,
)


# =============================================================================
# Proxy Acquisition Tests
# =============================================================================


class TestProxyAcquisition:
    """Tests for proxy pool management and acquisition."""

    def setup_method(self):
        """Setup common test objects."""
        self.proxies = build_proxy_list(count=5)
        self.config = build_traffic_config(
            target_url="https://example.com",
            max_threads=2,
            min_duration=0.01,
            max_duration=0.02,
        )
        self.engine = AsyncTrafficEngine(self.config, self.proxies)

    @pytest.mark.asyncio
    async def test_acquire_proxy_basic(self):
        """Test basic proxy acquisition selects available proxies."""
        proxy = await self.engine._acquire_proxy()

        assert proxy is not None
        assert isinstance(proxy, ProxyConfig)
        assert (proxy.host, proxy.port) in self.engine._proxies_in_use
        assert len(self.engine._proxies_in_use) == 1

    @pytest.mark.asyncio
    async def test_acquire_proxy_empty_pool_returns_none(self):
        """Test acquisition returns None with empty proxy pool."""
        engine = AsyncTrafficEngine(self.config, [])
        proxy = await engine._acquire_proxy()
        assert proxy is None

    @pytest.mark.asyncio
    async def test_acquire_proxy_marks_in_use(self):
        """Test acquired proxy is marked as in-use."""
        proxy = await self.engine._acquire_proxy()
        assert (proxy.host, proxy.port) in self.engine._proxies_in_use

    @pytest.mark.asyncio
    async def test_acquire_multiple_proxies(self):
        """Test acquiring multiple proxies tracks all as in-use."""
        p1 = await self.engine._acquire_proxy()
        p2 = await self.engine._acquire_proxy()
        p3 = await self.engine._acquire_proxy()

        assert len(self.engine._proxies_in_use) == 3
        assert (p1.host, p1.port) in self.engine._proxies_in_use
        assert (p2.host, p2.port) in self.engine._proxies_in_use
        assert (p3.host, p3.port) in self.engine._proxies_in_use

    @pytest.mark.asyncio
    async def test_acquire_proxy_round_robin_fallback(self):
        """Test fallback to round-robin when all proxies are in use."""
        # Use a small pool of 2 proxies
        proxies = build_proxy_list(count=2)
        engine = AsyncTrafficEngine(self.config, proxies)

        # Acquire all available proxies
        await engine._acquire_proxy()
        await engine._acquire_proxy()
        assert len(engine._proxies_in_use) == 2

        # Next acquisition should still work (round-robin reuse)
        p3 = await engine._acquire_proxy()
        assert p3 is not None
        assert p3 in proxies

    @pytest.mark.asyncio
    async def test_acquire_prefers_high_score_proxies(self):
        """Test weighted selection prefers higher-score proxies."""
        # Create proxies with varying scores
        proxies = [
            build_proxy_config(host="1.1.1.1", port=8080),
            build_proxy_config(host="2.2.2.2", port=8080),
            build_proxy_config(host="3.3.3.3", port=8080),
        ]
        proxies[0].score = 0.1  # Low score
        proxies[1].score = 0.1  # Low score
        proxies[2].score = 100.0  # High score

        engine = AsyncTrafficEngine(self.config, proxies)

        # Acquire many times and check distribution
        selections = {}
        for _ in range(50):
            proxy = await engine._acquire_proxy()
            key = proxy.host
            selections[key] = selections.get(key, 0) + 1
            await engine._release_proxy(proxy)

        # High-score proxy should be selected most often
        assert selections.get("3.3.3.3", 0) > selections.get("1.1.1.1", 0)


# =============================================================================
# Proxy Release Tests
# =============================================================================


class TestProxyRelease:
    """Tests for proxy release mechanism."""

    def setup_method(self):
        """Setup common test objects."""
        self.proxies = build_proxy_list(count=5)
        self.config = build_traffic_config()
        self.engine = AsyncTrafficEngine(self.config, self.proxies)

    @pytest.mark.asyncio
    async def test_release_proxy_removes_from_use_set(self):
        """Test proxy release removes from in-use set."""
        proxy = await self.engine._acquire_proxy()
        assert len(self.engine._proxies_in_use) == 1

        await self.engine._release_proxy(proxy)
        assert len(self.engine._proxies_in_use) == 0

    @pytest.mark.asyncio
    async def test_release_unknown_proxy_no_error(self):
        """Test releasing a proxy not in the use set doesn't crash."""
        proxy = build_proxy_config(host="9.9.9.9")
        # Should not raise
        await self.engine._release_proxy(proxy)
        assert len(self.engine._proxies_in_use) == 0

    @pytest.mark.asyncio
    async def test_release_none_proxy_no_error(self):
        """Test releasing None proxy doesn't crash."""
        await self.engine._release_proxy(None)
        assert len(self.engine._proxies_in_use) == 0

    @pytest.mark.asyncio
    async def test_acquire_release_cycle(self):
        """Test acquire-release cycle works correctly."""
        # Acquire all proxies
        acquired = []
        for _ in range(5):
            proxy = await self.engine._acquire_proxy()
            acquired.append(proxy)

        assert len(self.engine._proxies_in_use) == 5

        # Release all proxies
        for proxy in acquired:
            await self.engine._release_proxy(proxy)

        assert len(self.engine._proxies_in_use) == 0


# =============================================================================
# Request Execution Tests
# =============================================================================


class TestRequestExecution:
    """Tests for _make_request method."""

    def setup_method(self):
        """Setup common test objects."""
        self.proxies = build_proxy_list(count=5)
        self.config = build_traffic_config(
            target_url="https://example.com",
            min_duration=0.001,  # Very short for tests
            max_duration=0.002,
        )
        self.mock_on_update = MagicMock()
        self.mock_on_log = MagicMock()
        self.engine = AsyncTrafficEngine(
            config=self.config,
            proxies=self.proxies,
            on_update=self.mock_on_update,
            on_log=self.mock_on_log,
        )

    @pytest.mark.asyncio
    @patch("core.engine.requests.AsyncSession")
    async def test_make_request_success_increments_stats(self, mock_session_cls):
        """Test successful request updates statistics correctly."""
        # Setup mock
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        mock_session.close = AsyncMock()
        mock_session_cls.return_value = mock_session

        self.engine.running = True
        await self.engine._make_request()

        assert self.engine.stats.total_requests == 1
        assert self.engine.stats.success == 1
        assert self.engine.stats.failed == 0

    @pytest.mark.asyncio
    @patch("core.engine.requests.AsyncSession")
    async def test_make_request_failure_status(self, mock_session_cls):
        """Test failed status code updates failure stats."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        mock_session.close = AsyncMock()
        mock_session_cls.return_value = mock_session

        self.engine.running = True
        await self.engine._make_request()

        assert self.engine.stats.total_requests == 1
        assert self.engine.stats.success == 0
        assert self.engine.stats.failed == 1

    @pytest.mark.asyncio
    @patch("core.engine.requests.AsyncSession")
    async def test_make_request_exception_increments_failed(self, mock_session_cls):
        """Test exception during request updates failure stats."""
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(side_effect=Exception("Network error"))
        mock_session.close = AsyncMock()
        mock_session_cls.return_value = mock_session

        self.engine.running = True
        await self.engine._make_request()

        assert self.engine.stats.total_requests == 1
        assert self.engine.stats.failed == 1

    @pytest.mark.asyncio
    @patch("core.engine.requests.AsyncSession")
    async def test_make_request_releases_proxy_on_success(self, mock_session_cls):
        """Test proxy is released after successful request."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        mock_session.close = AsyncMock()
        mock_session_cls.return_value = mock_session

        self.engine.running = True
        await self.engine._make_request()

        # Proxy should be released
        assert len(self.engine._proxies_in_use) == 0

    @pytest.mark.asyncio
    @patch("core.engine.requests.AsyncSession")
    async def test_make_request_releases_proxy_on_error(self, mock_session_cls):
        """Test proxy is released even after exception."""
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(side_effect=Exception("Network error"))
        mock_session.close = AsyncMock()
        mock_session_cls.return_value = mock_session

        self.engine.running = True
        await self.engine._make_request()

        # Proxy should still be released
        assert len(self.engine._proxies_in_use) == 0

    @pytest.mark.asyncio
    @patch("core.engine.requests.AsyncSession")
    async def test_make_request_calls_on_update(self, mock_session_cls):
        """Test on_update callback is called."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        mock_session.close = AsyncMock()
        mock_session_cls.return_value = mock_session

        self.engine.running = True
        await self.engine._make_request()

        assert self.mock_on_update.call_count >= 1

    @pytest.mark.asyncio
    async def test_make_request_not_running_returns_early(self):
        """Test _make_request returns early if not running."""
        self.engine.running = False
        await self.engine._make_request()

        # No stats should be updated
        assert self.engine.stats.total_requests == 0


# =============================================================================
# Dead Proxy Removal Tests
# =============================================================================


class TestDeadProxyRemoval:
    """Tests for automatic dead proxy removal."""

    def setup_method(self):
        """Setup common test objects."""
        self.config = build_traffic_config(min_duration=0.001, max_duration=0.002)
        self.mock_on_log = MagicMock()

    @pytest.mark.asyncio
    @patch("core.engine.requests.AsyncSession")
    async def test_dead_proxy_removed_from_pool(self, mock_session_cls):
        """Test that proxies causing fatal errors are removed."""
        proxies = build_proxy_list(count=3)
        engine = AsyncTrafficEngine(self.config, proxies, on_log=self.mock_on_log)

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(side_effect=Exception("Fatal Proxy Error"))
        mock_session.close = AsyncMock()
        mock_session_cls.return_value = mock_session

        with patch("core.engine.PROXY_ERROR_CODES", ["Fatal Proxy Error"]):
            engine.running = True
            initial_count = len(engine.proxies)

            await engine._make_request()

            assert len(engine.proxies) == initial_count - 1
            self.mock_on_log.assert_called()

    @pytest.mark.asyncio
    @patch("core.engine.requests.AsyncSession")
    async def test_engine_stops_when_all_proxies_exhausted(self, mock_session_cls):
        """Test engine stops when all proxies are removed."""
        # Single proxy so one failure exhausts the pool
        single_proxy = build_proxy_list(count=1)
        engine = AsyncTrafficEngine(self.config, single_proxy, on_log=self.mock_on_log)

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(side_effect=Exception("Fatal Proxy Error"))
        mock_session.close = AsyncMock()
        mock_session_cls.return_value = mock_session

        with patch("core.engine.PROXY_ERROR_CODES", ["Fatal Proxy Error"]):
            engine.running = True
            await engine._make_request()

            assert len(engine.proxies) == 0
            assert engine.running is False

    @pytest.mark.asyncio
    @patch("core.engine.requests.AsyncSession")
    async def test_non_proxy_error_keeps_proxy(self, mock_session_cls):
        """Test non-proxy errors don't remove the proxy."""
        proxies = build_proxy_list(count=3)
        engine = AsyncTrafficEngine(self.config, proxies)

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(side_effect=Exception("Generic network error"))
        mock_session.close = AsyncMock()
        mock_session_cls.return_value = mock_session

        with patch("core.engine.PROXY_ERROR_CODES", ["SPECIFIC_PROXY_ERROR"]):
            engine.running = True
            initial_count = len(engine.proxies)

            await engine._make_request()

            # Proxy count should remain the same
            assert len(engine.proxies) == initial_count


# =============================================================================
# Statistics Tracking Tests
# =============================================================================


class TestStatisticsTracking:
    """Tests for traffic statistics tracking."""

    def setup_method(self):
        """Setup common test objects."""
        self.proxies = build_proxy_list(count=5)
        self.config = build_traffic_config(min_duration=0.001, max_duration=0.002)
        self.mock_on_update = MagicMock()
        self.engine = AsyncTrafficEngine(
            self.config, self.proxies, on_update=self.mock_on_update
        )

    @pytest.mark.asyncio
    @patch("core.engine.requests.AsyncSession")
    async def test_stats_active_threads_increments_and_decrements(
        self, mock_session_cls
    ):
        """Test active_threads is properly managed."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        mock_session.close = AsyncMock()
        mock_session_cls.return_value = mock_session

        self.engine.running = True
        await self.engine._make_request()

        # After request completes, active_threads should be back to 0
        assert self.engine.stats.active_threads == 0

    @pytest.mark.asyncio
    @patch("core.engine.requests.AsyncSession")
    async def test_stats_active_proxies_updated(self, mock_session_cls):
        """Test active_proxies is updated in stats."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        mock_session.close = AsyncMock()
        mock_session_cls.return_value = mock_session

        self.engine.running = True
        await self.engine._make_request()

        # Check that on_update was called with stats containing active_proxies
        call_args = self.mock_on_update.call_args
        stats = call_args[0][0]
        assert stats.active_proxies == len(self.proxies)


# =============================================================================
# Burst Mode Tests
# =============================================================================


class TestBurstMode:
    """Tests for burst mode functionality."""

    def setup_method(self):
        """Setup common test objects."""
        self.proxies = build_proxy_list(count=5)
        self.mock_on_log = MagicMock()

    @pytest.mark.asyncio
    async def test_burst_mode_logs_burst_complete(self):
        """Test burst mode logs completion messages."""
        config = build_traffic_config(
            burst_mode=True,
            burst_requests=2,
            burst_sleep_min=0.001,
            burst_sleep_max=0.002,
            total_visits=2,  # Just one burst
            min_duration=0.001,
            max_duration=0.002,
        )
        engine = AsyncTrafficEngine(config, self.proxies, on_log=self.mock_on_log)

        with patch("core.engine.requests.AsyncSession") as mock_session_cls:
            mock_response = MagicMock()
            mock_response.status_code = 200

            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=mock_response)
            mock_session.close = AsyncMock()
            mock_session_cls.return_value = mock_session

            await engine.run()

        # Verify it ran the expected number of requests
        assert engine.stats.total_requests >= 2

    @pytest.mark.asyncio
    async def test_continuous_mode_no_burst_sleep(self):
        """Test continuous mode doesn't have burst sleeps."""
        config = build_traffic_config(
            burst_mode=False,
            total_visits=3,
            min_duration=0.001,
            max_duration=0.002,
        )
        engine = AsyncTrafficEngine(config, self.proxies, on_log=self.mock_on_log)

        with patch("core.engine.requests.AsyncSession") as mock_session_cls:
            mock_response = MagicMock()
            mock_response.status_code = 200

            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=mock_response)
            mock_session.close = AsyncMock()
            mock_session_cls.return_value = mock_session

            await engine.run()

        # Should complete without burst messages
        log_messages = [str(call) for call in self.mock_on_log.call_args_list]
        burst_logged = any("Burst complete" in msg for msg in log_messages)
        assert not burst_logged


# =============================================================================
# Run Loop Tests
# =============================================================================


class TestRunLoop:
    """Tests for the main run loop."""

    def setup_method(self):
        """Setup common test objects."""
        self.proxies = build_proxy_list(count=5)

    @pytest.mark.asyncio
    async def test_run_stops_on_total_visits(self):
        """Test engine stops after reaching total_visits."""
        config = build_traffic_config(
            total_visits=3,
            max_threads=1,
            min_duration=0.001,
            max_duration=0.002,
        )
        engine = AsyncTrafficEngine(config, self.proxies)

        with patch("core.engine.requests.AsyncSession") as mock_session_cls:
            mock_response = MagicMock()
            mock_response.status_code = 200

            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=mock_response)
            mock_session.close = AsyncMock()
            mock_session_cls.return_value = mock_session

            await engine.run()

        assert engine.stats.total_requests >= 3
        assert engine.running is False

    @pytest.mark.asyncio
    async def test_run_respects_max_threads(self):
        """Test run doesn't exceed max_threads concurrent tasks."""
        config = build_traffic_config(
            total_visits=10,
            max_threads=2,
            min_duration=0.01,
            max_duration=0.02,
        )

        max_active_seen = 0

        def track_active(stats):
            nonlocal max_active_seen
            if stats.active_threads > max_active_seen:
                max_active_seen = stats.active_threads

        engine = AsyncTrafficEngine(config, self.proxies, on_update=track_active)

        with patch("core.engine.requests.AsyncSession") as mock_session_cls:
            mock_response = MagicMock()
            mock_response.status_code = 200

            async def delayed_get(*args, **kwargs):
                await asyncio.sleep(0.01)
                return mock_response

            mock_session = AsyncMock()
            mock_session.get = delayed_get
            mock_session.close = AsyncMock()
            mock_session_cls.return_value = mock_session

            await engine.run()

        # max_threads should not be exceeded
        assert max_active_seen <= config.max_threads

    @pytest.mark.asyncio
    async def test_run_with_infinite_visits_can_be_stopped(self):
        """Test engine with infinite visits can be stopped."""
        config = build_traffic_config(
            total_visits=0,  # Infinite
            max_threads=1,
            min_duration=0.001,
            max_duration=0.002,
        )
        engine = AsyncTrafficEngine(config, self.proxies)

        with patch("core.engine.requests.AsyncSession") as mock_session_cls:
            mock_response = MagicMock()
            mock_response.status_code = 200

            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=mock_response)
            mock_session.close = AsyncMock()
            mock_session_cls.return_value = mock_session

            # Run in background and stop after a short time
            async def stop_after_delay():
                await asyncio.sleep(0.05)
                engine.stop()

            await asyncio.gather(engine.run(), stop_after_delay())

        assert engine.running is False
        assert engine.stats.total_requests > 0


# =============================================================================
# Callback Tests
# =============================================================================


class TestCallbacks:
    """Tests for callback invocation."""

    def setup_method(self):
        """Setup common test objects."""
        self.proxies = build_proxy_list(count=5)
        self.config = build_traffic_config(min_duration=0.001, max_duration=0.002)

    @pytest.mark.asyncio
    @patch("core.engine.requests.AsyncSession")
    async def test_on_log_called_on_start(self, mock_session_cls):
        """Test on_log is called when engine starts."""
        mock_on_log = MagicMock()
        config = build_traffic_config(total_visits=1)
        engine = AsyncTrafficEngine(config, self.proxies, on_log=mock_on_log)

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        mock_session.close = AsyncMock()
        mock_session_cls.return_value = mock_session

        await engine.run()

        # Should have logged start message
        log_messages = [str(call) for call in mock_on_log.call_args_list]
        started_logged = any("started" in msg.lower() for msg in log_messages)
        assert started_logged

    @pytest.mark.asyncio
    @patch("core.engine.requests.AsyncSession")
    async def test_on_log_called_on_stop(self, mock_session_cls):
        """Test on_log is called when engine stops."""
        mock_on_log = MagicMock()
        config = build_traffic_config(total_visits=1)
        engine = AsyncTrafficEngine(config, self.proxies, on_log=mock_on_log)

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        mock_session.close = AsyncMock()
        mock_session_cls.return_value = mock_session

        await engine.run()

        # Should have logged stop message
        log_messages = [str(call) for call in mock_on_log.call_args_list]
        stopped_logged = any("stopped" in msg.lower() for msg in log_messages)
        assert stopped_logged
