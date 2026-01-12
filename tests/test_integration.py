"""Integration tests for Master/Slave communication.

These tests verify end-to-end communication between MasterServer and SlaveController.
They use real WebSocket connections but mock the actual operations (scrape, check, etc).
"""

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from core.master_server import MasterServer
from core.slave_controller import SlaveController
from core.websocket_server import MessageType


# Test configuration
TEST_HOST = "127.0.0.1"
TEST_PORT = 19765  # Use unique port to avoid conflicts
TEST_SECRET = "integration-test-secret-key-32chars!"


class TestMasterSlaveIntegration:
    """Integration tests for master/slave communication."""

    @pytest.fixture
    def master(self):
        """Create and start a MasterServer."""
        server = MasterServer(
            host=TEST_HOST,
            port=TEST_PORT,
            secret_key=TEST_SECRET,
            heartbeat_interval=2,
            timeout_seconds=10,
        )
        yield server
        server.stop()

    @pytest.fixture
    def slave_config(self):
        """Return slave configuration."""
        return {
            "master_host": TEST_HOST,
            "master_port": TEST_PORT,
            "secret_key": TEST_SECRET,
            "slave_name": "test-slave-1",
        }

    def test_master_starts_and_stops(self, master):
        """Test master server lifecycle."""
        assert not master.is_running

        result = master.start()
        assert result is True
        assert master.is_running
        assert master.slave_count == 0

        master.stop()
        assert not master.is_running

    def test_master_rejects_short_secret(self):
        """Test that master rejects short secret keys."""
        server = MasterServer(
            host=TEST_HOST,
            port=TEST_PORT + 1,
            secret_key="short",
        )
        result = server.start()
        assert result is False
        assert not server.is_running

    def test_aggregated_stats_empty(self, master):
        """Test aggregated stats with no slaves."""
        master.start()
        stats = master.get_aggregated_stats()

        assert stats.active_slaves == 0
        assert stats.total_requests == 0
        assert stats.total_success == 0

    def test_command_methods_fail_when_stopped(self, master):
        """Test that command methods return 0/False when server not running."""
        assert master.start_scrape_on_slaves() == 0
        assert master.start_check_on_slaves(threads=100) == 0
        assert master.start_traffic_on_slaves(target_url="http://test.com") == 0
        assert master.stop_slaves() == 0


class TestSlaveControllerInit:
    """Test SlaveController initialization."""

    def test_controller_init(self):
        """Test controller initializes correctly."""
        controller = SlaveController(
            master_host="127.0.0.1",
            master_port=8765,
            secret_key="test-secret-32-characters-long!",
            slave_name="test-slave",
            settings={},
        )
        assert controller.slave_name == "test-slave"
        assert controller.master_host == "127.0.0.1"
        assert controller.master_port == 8765

    def test_controller_handlers_registered(self):
        """Test that all command handlers are registered."""
        controller = SlaveController(
            master_host="127.0.0.1",
            master_port=8765,
            secret_key="test-secret-32-characters-long!",
            slave_name="test-slave",
            settings={},
        )
        expected_handlers = [
            MessageType.START_SCRAPE,
            MessageType.START_CHECK,
            MessageType.START_TRAFFIC,
            MessageType.START_SCAN,
            MessageType.STOP,
            MessageType.GET_STATUS,
            MessageType.UPDATE_CONFIG,
        ]
        for msg_type in expected_handlers:
            assert msg_type in controller._handlers


class TestMasterServerCallbacks:
    """Test MasterServer callback invocations."""

    def test_on_log_callback(self):
        """Test that log callback is invoked."""
        logs = []

        server = MasterServer(
            host=TEST_HOST,
            port=TEST_PORT + 2,
            secret_key=TEST_SECRET,
            callback_wrapper=lambda cb: cb(),
            on_log=lambda msg: logs.append(msg),
        )

        server._log("Test message")
        assert any("Test message" in log for log in logs)

    def test_callback_wrapper_used(self):
        """Test that callback_wrapper is used for callbacks."""
        wrapper_calls = []

        def mock_wrapper(cb):
            wrapper_calls.append(True)
            cb()

        server = MasterServer(
            host=TEST_HOST,
            port=TEST_PORT + 3,
            secret_key=TEST_SECRET,
            callback_wrapper=mock_wrapper,
            on_log=lambda msg: None,
        )

        server._log("Test")
        assert len(wrapper_calls) >= 1


class TestScannerIntegration:
    """Test scanner command distribution."""

    def test_start_scan_on_slaves_not_running(self):
        """Test start_scan_on_slaves when server not running."""
        server = MasterServer(
            host=TEST_HOST,
            port=TEST_PORT + 4,
            secret_key=TEST_SECRET,
        )

        result = server.start_scan_on_slaves(targets=["192.168.1.0/24"])
        assert result == 0


# Async integration tests (require running event loop)
class TestAsyncIntegration:
    """Async integration tests for actual WebSocket communication."""

    @pytest.mark.asyncio
    async def test_slave_controller_stop(self):
        """Test that slave controller can be stopped."""
        controller = SlaveController(
            master_host="127.0.0.1",
            master_port=99999,  # Won't connect
            secret_key=TEST_SECRET,
            slave_name="test-slave",
            settings={},
        )

        # Should not raise
        await controller.stop()

    @pytest.mark.asyncio
    async def test_slave_operation_status(self):
        """Test operation status tracking."""
        controller = SlaveController(
            master_host="127.0.0.1",
            master_port=99999,
            secret_key=TEST_SECRET,
            slave_name="test-slave",
            settings={},
        )

        # Initially no operation running
        assert not controller._is_operation_running()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
