"""Tests for MasterServer class."""

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from core.master_server import AggregatedStats, MasterServer, SlaveStats
from core.websocket_server import MessageType


class TestDataClasses:
    """Test SlaveStats and AggregatedStats dataclasses."""

    def test_slave_stats_defaults(self):
        """Test SlaveStats default values."""
        stats = SlaveStats(
            slave_id="test-id",
            slave_name="test-slave",
            ip_address="192.168.1.1",
            connected_at=1000.0,
            last_heartbeat=1000.0,
        )
        assert stats.slave_id == "test-id"
        assert stats.slave_name == "test-slave"
        assert stats.status == "idle"
        assert stats.requests == 0
        assert stats.cpu_percent == 0.0

    def test_aggregated_stats_defaults(self):
        """Test AggregatedStats default values."""
        stats = AggregatedStats()
        assert stats.active_slaves == 0
        assert stats.total_requests == 0
        assert stats.total_success == 0
        assert stats.avg_cpu == 0.0


class TestMasterServerInit:
    """Test MasterServer initialization."""

    def test_init_with_valid_secret(self):
        """Test initialization with valid secret key."""
        server = MasterServer(
            host="127.0.0.1",
            port=8765,
            secret_key="a" * 32,
        )
        assert server.host == "127.0.0.1"
        assert server.port == 8765
        assert server.secret_key == "a" * 32
        assert not server.is_running
        assert server.slave_count == 0

    def test_init_properties(self):
        """Test server properties."""
        server = MasterServer(
            host="0.0.0.0",
            port=9000,
            secret_key="b" * 32,
        )
        assert server.server_address == "0.0.0.0:9000"
        assert not server.is_running


class TestMasterServerValidation:
    """Test MasterServer input validation."""

    def test_start_fails_with_short_secret(self):
        """Test that start fails with short secret key."""
        server = MasterServer(
            host="127.0.0.1",
            port=8765,
            secret_key="short",
        )
        result = server.start()
        assert not result
        assert not server.is_running

    def test_start_fails_with_empty_secret(self):
        """Test that start fails with empty secret key."""
        server = MasterServer(
            host="127.0.0.1",
            port=8765,
            secret_key="",
        )
        result = server.start()
        assert not result


class TestSlaveStatsTracking:
    """Test slave stats tracking functionality."""

    def test_get_slaves_empty(self):
        """Test get_slaves returns empty list when no slaves."""
        server = MasterServer(secret_key="a" * 32)
        assert server.get_slaves() == []

    def test_get_slave_not_found(self):
        """Test get_slave returns None for unknown slave."""
        server = MasterServer(secret_key="a" * 32)
        assert server.get_slave("unknown-id") is None

    def test_aggregated_stats_empty(self):
        """Test aggregated stats with no slaves."""
        server = MasterServer(secret_key="a" * 32)
        stats = server.get_aggregated_stats()
        assert stats.active_slaves == 0
        assert stats.total_requests == 0

    def test_slave_stats_aggregation(self):
        """Test stats aggregation from multiple slaves."""
        server = MasterServer(secret_key="a" * 32)

        # Manually add slave stats for testing
        server._slave_stats["slave1"] = SlaveStats(
            slave_id="slave1",
            slave_name="Slave 1",
            ip_address="1.1.1.1",
            connected_at=time.time(),
            last_heartbeat=time.time(),
            requests=100,
            success=90,
            failed=10,
            cpu_percent=50.0,
            memory_percent=60.0,
        )
        server._slave_stats["slave2"] = SlaveStats(
            slave_id="slave2",
            slave_name="Slave 2",
            ip_address="2.2.2.2",
            connected_at=time.time(),
            last_heartbeat=time.time(),
            requests=200,
            success=180,
            failed=20,
            cpu_percent=70.0,
            memory_percent=80.0,
        )

        stats = server.get_aggregated_stats()
        assert stats.active_slaves == 2
        assert stats.total_requests == 300
        assert stats.total_success == 270
        assert stats.total_failed == 30
        assert stats.avg_cpu == 60.0  # (50 + 70) / 2
        assert stats.avg_memory == 70.0  # (60 + 80) / 2


class TestCallbackWrapper:
    """Test callback wrapper functionality."""

    def test_callback_wrapper_called(self):
        """Test that callback wrapper is invoked."""
        wrapper_called = []

        def mock_wrapper(cb):
            wrapper_called.append(True)
            cb()

        server = MasterServer(
            secret_key="a" * 32,
            callback_wrapper=mock_wrapper,
            on_log=lambda msg: None,
        )

        # Trigger a log message
        server._log("test message")

        assert len(wrapper_called) == 1

    def test_on_log_callback(self):
        """Test on_log callback is invoked."""
        log_messages = []

        def capture_log(msg):
            log_messages.append(msg)

        server = MasterServer(
            secret_key="a" * 32,
            callback_wrapper=lambda cb: cb(),  # Execute immediately
            on_log=capture_log,
        )

        server._log("test message")
        assert "test message" in log_messages


class TestMessageHandlers:
    """Test message handler methods."""

    def test_handle_slave_connected(self):
        """Test slave connection handling."""
        connected_slaves = []

        def on_connected(slave_id, info):
            connected_slaves.append((slave_id, info))

        server = MasterServer(
            secret_key="a" * 32,
            callback_wrapper=lambda cb: cb(),
            on_slave_connected=on_connected,
        )

        server._handle_slave_connected("slave-123", {
            "name": "Test Slave",
            "ip": "192.168.1.100",
            "connected_at": 1000.0,
        })

        assert "slave-123" in server._slave_stats
        assert server._slave_stats["slave-123"].slave_name == "Test Slave"
        assert len(connected_slaves) == 1

    def test_handle_slave_disconnected(self):
        """Test slave disconnection handling."""
        disconnected_slaves = []

        def on_disconnected(slave_id):
            disconnected_slaves.append(slave_id)

        server = MasterServer(
            secret_key="a" * 32,
            callback_wrapper=lambda cb: cb(),
            on_slave_disconnected=on_disconnected,
        )

        # Add a slave first
        server._slave_stats["slave-123"] = SlaveStats(
            slave_id="slave-123",
            slave_name="Test",
            ip_address="1.1.1.1",
            connected_at=time.time(),
            last_heartbeat=time.time(),
        )

        server._handle_slave_disconnected("slave-123")

        assert "slave-123" not in server._slave_stats
        assert "slave-123" in disconnected_slaves

    def test_update_slave_status(self):
        """Test slave status update."""
        server = MasterServer(secret_key="a" * 32)

        server._slave_stats["slave-1"] = SlaveStats(
            slave_id="slave-1",
            slave_name="Test",
            ip_address="1.1.1.1",
            connected_at=time.time(),
            last_heartbeat=time.time(),
        )

        server._update_slave_status("slave-1", {
            "status": "scraping",
            "operation": "proxy scrape",
            "cpu_percent": 45.5,
            "memory_percent": 62.3,
        })

        stats = server._slave_stats["slave-1"]
        assert stats.status == "scraping"
        assert stats.current_operation == "proxy scrape"
        assert stats.cpu_percent == 45.5
        assert stats.memory_percent == 62.3

    def test_update_traffic_stats(self):
        """Test traffic stats update."""
        server = MasterServer(secret_key="a" * 32)

        server._slave_stats["slave-1"] = SlaveStats(
            slave_id="slave-1",
            slave_name="Test",
            ip_address="1.1.1.1",
            connected_at=time.time(),
            last_heartbeat=time.time(),
        )

        server._update_traffic_stats("slave-1", {
            "total_requests": 1000,
            "success": 950,
            "failed": 50,
        })

        stats = server._slave_stats["slave-1"]
        assert stats.status == "traffic"
        assert stats.requests == 1000
        assert stats.success == 950
        assert stats.failed == 50


class TestCommandDistribution:
    """Test command distribution methods (without actual server)."""

    def test_send_command_when_not_running(self):
        """Test send_command returns False when server not running."""
        server = MasterServer(secret_key="a" * 32)
        result = server.send_command("slave-1", MessageType.START_SCRAPE, {})
        assert not result

    def test_broadcast_command_when_not_running(self):
        """Test broadcast_command returns 0 when server not running."""
        server = MasterServer(secret_key="a" * 32)
        result = server.broadcast_command(MessageType.START_SCRAPE, {})
        assert result == 0

    def test_start_scrape_on_slaves_not_running(self):
        """Test start_scrape_on_slaves when not running."""
        server = MasterServer(secret_key="a" * 32)
        result = server.start_scrape_on_slaves()
        assert result == 0

    def test_start_check_on_slaves_not_running(self):
        """Test start_check_on_slaves when not running."""
        server = MasterServer(secret_key="a" * 32)
        result = server.start_check_on_slaves(threads=100)
        assert result == 0

    def test_start_traffic_on_slaves_not_running(self):
        """Test start_traffic_on_slaves when not running."""
        server = MasterServer(secret_key="a" * 32)
        result = server.start_traffic_on_slaves(target_url="http://test.com")
        assert result == 0

    def test_stop_slaves_not_running(self):
        """Test stop_slaves when not running."""
        server = MasterServer(secret_key="a" * 32)
        result = server.stop_slaves()
        assert result == 0


class TestServerLifecycle:
    """Test server start/stop lifecycle."""

    def test_stop_when_not_running(self):
        """Test stop when server not running does nothing."""
        server = MasterServer(secret_key="a" * 32)
        server.stop()  # Should not raise
        assert not server.is_running

    def test_double_start_fails(self):
        """Test that starting twice fails gracefully."""
        server = MasterServer(
            host="127.0.0.1",
            port=18765,
            secret_key="a" * 32,
        )

        # Manually set running state
        server._running = True

        # Second start should fail
        result = server.start()
        assert not result

        # Cleanup
        server._running = False
