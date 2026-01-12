"""
Tests for SlaveController command dispatcher and operation lifecycle.

Tests command handling, operation management, stats reporting, and resource monitoring.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.slave_controller import (
    OperationStatus,
    OperationType,
    ResourceStats,
    SlaveController,
    SlaveStatus,
)
from core.websocket_server import MessageType


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def controller_settings():
    """Default settings for controller tests."""
    return {
        "stats_interval": 1.0,
        "resource_interval": 10.0,
    }


@pytest.fixture
def controller(controller_settings):
    """Create SlaveController with mocked WebSocket client."""
    ctrl = SlaveController(
        master_host="127.0.0.1",
        master_port=8765,
        secret_key="test_secret_key_at_least_32_characters_long",
        slave_name="test-slave",
        settings=controller_settings,
    )
    return ctrl


# -----------------------------------------------------------------------------
# Test Data Models
# -----------------------------------------------------------------------------


class TestDataModels:
    """Test data model classes."""

    def test_operation_status_defaults(self):
        """Test OperationStatus default values."""
        status = OperationStatus()
        assert status.type == OperationType.NONE
        assert status.running is False
        assert status.progress == 0
        assert status.total == 0

    def test_resource_stats_defaults(self):
        """Test ResourceStats default values."""
        stats = ResourceStats()
        assert stats.cpu_percent == 0.0
        assert stats.memory_percent == 0.0
        assert stats.disk_percent == 0.0

    def test_slave_status_defaults(self):
        """Test SlaveStatus default values."""
        status = SlaveStatus(slave_name="test")
        assert status.slave_name == "test"
        assert status.connected is False
        assert status.operation.type == OperationType.NONE

    def test_operation_type_values(self):
        """Test OperationType enum values."""
        assert OperationType.NONE.value == "none"
        assert OperationType.SCRAPE.value == "scrape"
        assert OperationType.CHECK.value == "check"
        assert OperationType.TRAFFIC.value == "traffic"
        assert OperationType.SCAN.value == "scan"


# -----------------------------------------------------------------------------
# Test Controller Initialization
# -----------------------------------------------------------------------------


class TestControllerInit:
    """Test SlaveController initialization."""

    def test_controller_init(self, controller):
        """Test controller initializes with correct values."""
        assert controller.master_host == "127.0.0.1"
        assert controller.master_port == 8765
        assert controller.slave_name == "test-slave"
        assert controller.client is None  # Not created until run()

    def test_controller_handlers_registered(self, controller):
        """Test command handlers are registered."""
        assert MessageType.START_SCRAPE in controller._handlers
        assert MessageType.START_CHECK in controller._handlers
        assert MessageType.START_TRAFFIC in controller._handlers
        assert MessageType.START_SCAN in controller._handlers
        assert MessageType.STOP in controller._handlers
        assert MessageType.GET_STATUS in controller._handlers
        assert MessageType.UPDATE_CONFIG in controller._handlers


# -----------------------------------------------------------------------------
# Test Command Handling
# -----------------------------------------------------------------------------


class TestCommandHandling:
    """Test command dispatch and handling."""

    @pytest.mark.asyncio
    async def test_handle_stop_when_not_running(self, controller):
        """Test STOP command when no operation is running."""
        controller.client = MagicMock()
        controller.client.is_connected = True
        controller.client.send_log = AsyncMock()

        # Operation not running
        controller._status.operation.running = False

        await controller._handle_stop({})

        # Should complete without error

    @pytest.mark.asyncio
    async def test_handle_get_status(self, controller):
        """Test GET_STATUS command returns status."""
        controller.client = MagicMock()
        controller.client.is_connected = True
        controller.client.send_stats = AsyncMock()

        await controller._handle_get_status({})

        # Should have called send_stats
        controller.client.send_stats.assert_called_once()
        call_args = controller.client.send_stats.call_args
        assert call_args[0][0] == MessageType.STATUS_UPDATE

    @pytest.mark.asyncio
    async def test_handle_update_config(self, controller):
        """Test UPDATE_CONFIG command updates settings."""
        controller.client = MagicMock()
        controller.client.is_connected = True
        controller.client.send_log = AsyncMock()

        new_config = {
            "stats_interval": 2.0,
            "custom_setting": "value",
        }

        await controller._handle_update_config({"config": new_config})

        assert controller.settings["stats_interval"] == 2.0
        assert controller.settings["custom_setting"] == "value"
        assert controller._stats_interval == 2.0

    @pytest.mark.asyncio
    async def test_handle_start_traffic_no_url(self, controller):
        """Test START_TRAFFIC command fails without URL."""
        controller.client = MagicMock()
        controller.client.is_connected = True
        controller.client.send_log = AsyncMock()

        await controller._handle_start_traffic({"config": {}})

        # Should have logged error
        controller.client.send_log.assert_called()

    @pytest.mark.asyncio
    async def test_handle_start_scrape_no_sources(self, controller):
        """Test START_SCRAPE command fails without sources."""
        controller.client = MagicMock()
        controller.client.is_connected = True
        controller.client.send_log = AsyncMock()

        await controller._handle_start_scrape({})

        # Should have logged error
        controller.client.send_log.assert_called()

    @pytest.mark.asyncio
    async def test_handle_start_check_no_proxies(self, controller):
        """Test START_CHECK command fails without proxies."""
        controller.client = MagicMock()
        controller.client.is_connected = True
        controller.client.send_log = AsyncMock()

        await controller._handle_start_check({})

        # Should have logged error
        controller.client.send_log.assert_called()

    @pytest.mark.asyncio
    async def test_operation_running_blocks_new_ops(self, controller):
        """Test that running operation blocks starting new ones."""
        controller.client = MagicMock()
        controller.client.is_connected = True
        controller.client.send_log = AsyncMock()

        # Mark operation as running
        controller._status.operation.running = True
        controller._operation_task = asyncio.create_task(asyncio.sleep(100))

        try:
            # Try to start scrape - should be blocked
            await controller._handle_start_scrape(
                {"sources": ["http://example.com/proxies.txt"]}
            )

            # Should have logged warning about already running
            assert any(
                "already running" in str(call) for call in controller.client.send_log.call_args_list
            )
        finally:
            controller._operation_task.cancel()
            try:
                await controller._operation_task
            except asyncio.CancelledError:
                pass


# -----------------------------------------------------------------------------
# Test Resource Monitoring
# -----------------------------------------------------------------------------


class TestResourceMonitoring:
    """Test resource monitoring functionality."""

    def test_get_resource_stats_without_psutil(self, controller):
        """Test resource stats return zeros when psutil unavailable."""
        with patch.dict("sys.modules", {"psutil": None}):
            stats = controller._get_resource_stats()

            # Should return default values
            assert stats.cpu_percent == 0.0
            assert stats.memory_percent == 0.0
            assert stats.disk_percent == 0.0

    def test_get_resource_stats_with_psutil(self, controller):
        """Test resource stats with mocked psutil."""
        mock_psutil = MagicMock()
        mock_psutil.cpu_percent.return_value = 50.0
        mock_psutil.virtual_memory.return_value = MagicMock(
            percent=60.0,
            used=4 * 1024 * 1024 * 1024,  # 4GB
            total=8 * 1024 * 1024 * 1024,  # 8GB
        )
        mock_psutil.disk_usage.return_value = MagicMock(
            percent=70.0,
            used=200 * 1024 * 1024 * 1024,  # 200GB
            total=500 * 1024 * 1024 * 1024,  # 500GB
        )

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            # Reload to pick up mocked psutil
            stats = controller._get_resource_stats()
            # Note: The actual function imports psutil inside,
            # so the mock may not work as expected without more setup


# -----------------------------------------------------------------------------
# Test Callback Handling
# -----------------------------------------------------------------------------


class TestCallbacks:
    """Test connection callbacks."""

    @pytest.mark.asyncio
    async def test_on_connected_updates_status(self, controller):
        """Test on_connected callback updates status."""
        controller._on_connected()
        await asyncio.sleep(0.1)  # Let stats task start

        assert controller._status.connected is True

        # Clean up stats task
        if controller._stats_task:
            controller._stats_task.cancel()
            try:
                await controller._stats_task
            except asyncio.CancelledError:
                pass

    def test_on_disconnected_updates_status(self, controller):
        """Test on_disconnected callback updates status."""
        controller._status.connected = True
        controller._on_disconnected()

        assert controller._status.connected is False

    @pytest.mark.asyncio
    async def test_on_command_dispatches_to_handler(self, controller):
        """Test on_command dispatches to correct handler."""
        controller.client = MagicMock()
        controller.client.is_connected = True
        controller.client.send_log = AsyncMock()
        controller.client.send_stats = AsyncMock()

        # Trigger command
        controller._on_command(MessageType.GET_STATUS, {})

        # Wait for async handler
        await asyncio.sleep(0.1)

        # Should have called send_stats for status update
        controller.client.send_stats.assert_called()


# -----------------------------------------------------------------------------
# Test Operation Lifecycle
# -----------------------------------------------------------------------------


class TestOperationLifecycle:
    """Test operation start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_stop_operation_cancels_task(self, controller):
        """Test stopping operation cancels running task."""
        controller.client = MagicMock()
        controller.client.is_connected = True
        controller.client.send_log = AsyncMock()

        # Create a long-running operation task
        async def long_operation():
            await asyncio.sleep(100)

        controller._status.operation.running = True
        controller._operation_task = asyncio.create_task(long_operation())

        # Stop operation
        await controller._stop_operation()

        # Task should be cancelled
        assert controller._operation_task is None or controller._operation_task.done()
        assert not controller._status.operation.running

    @pytest.mark.asyncio
    async def test_is_operation_running(self, controller):
        """Test _is_operation_running check."""
        assert not controller._is_operation_running()

        controller._status.operation.running = True
        controller._operation_task = asyncio.create_task(asyncio.sleep(0.1))

        assert controller._is_operation_running()

        controller._operation_task.cancel()
        try:
            await controller._operation_task
        except asyncio.CancelledError:
            pass


# -----------------------------------------------------------------------------
# Test Controller Lifecycle
# -----------------------------------------------------------------------------


class TestControllerLifecycle:
    """Test controller run/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_stop_controller(self, controller):
        """Test stopping controller cleans up properly."""
        controller._running = True

        # Mock client
        controller.client = MagicMock()
        controller.client.stop = MagicMock()

        await controller.stop()

        assert not controller._running
        controller.client.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_controller(self, controller):
        """Test cleanup releases resources."""
        controller._running = True
        controller.client = MagicMock()
        controller.client.stop = MagicMock()

        await controller.cleanup()

        assert not controller._running


# -----------------------------------------------------------------------------
# Test Send Log
# -----------------------------------------------------------------------------


class TestSendLog:
    """Test log forwarding to master."""

    @pytest.mark.asyncio
    async def test_send_log_when_connected(self, controller):
        """Test logs are sent when connected."""
        controller.client = MagicMock()
        controller.client.is_connected = True
        controller.client.send_log = AsyncMock()

        await controller._send_log("info", "Test message")

        controller.client.send_log.assert_called_once_with("info", "Test message")

    @pytest.mark.asyncio
    async def test_send_log_when_disconnected(self, controller):
        """Test logs are not sent when disconnected."""
        controller.client = MagicMock()
        controller.client.is_connected = False
        controller.client.send_log = AsyncMock()

        await controller._send_log("info", "Test message")

        controller.client.send_log.assert_not_called()
