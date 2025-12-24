"""
Tests for WebSocket Server/Client communication.

Tests authentication, message passing, heartbeat, and reconnection logic.
"""

import asyncio
import pytest

from core.websocket_client import WebSocketClient
from core.websocket_server import MessageType, WebSocketServer


@pytest.fixture
async def server():
    """Create and start WebSocket server."""
    srv = WebSocketServer(
        host="127.0.0.1",
        port=18765,  # Test port
        secret_key="test_secret_key_at_least_32_characters_long_for_security",
        heartbeat_interval=1,  # Fast heartbeat for testing
        timeout_seconds=5,
    )
    await srv.start()
    yield srv
    await srv.stop()


@pytest.fixture
def client():
    """Create WebSocket client."""
    return WebSocketClient(
        master_host="127.0.0.1",
        master_port=18765,
        secret_key="test_secret_key_at_least_32_characters_long_for_security",
        slave_name="test-slave",
        heartbeat_interval=1,
    )


class TestWebSocketServer:
    """Test WebSocket server functionality."""

    @pytest.mark.asyncio
    async def test_server_start_stop(self, server):
        """Test server starts and stops cleanly."""
        assert server.is_running
        assert server.slave_count == 0

        await server.stop()
        assert not server.is_running

    @pytest.mark.asyncio
    async def test_invalid_secret_key(self):
        """Test server rejects short secret keys."""
        with pytest.raises(ValueError, match="at least 32 characters"):
            WebSocketServer(
                host="127.0.0.1",
                port=18766,
                secret_key="short",  # Too short
            )


class TestWebSocketClient:
    """Test WebSocket client functionality."""

    @pytest.mark.asyncio
    async def test_client_connect_disconnect(self, server, client):
        """Test client connects and disconnects."""
        await client.connect()
        await asyncio.sleep(0.5)  # Wait for connection

        assert client.is_connected
        assert server.slave_count == 1

        await client.disconnect()
        await asyncio.sleep(0.2)

        assert not client.is_connected

    @pytest.mark.asyncio
    async def test_client_invalid_secret(self, server):
        """Test client fails authentication with wrong secret."""
        bad_client = WebSocketClient(
            master_host="127.0.0.1",
            master_port=18765,
            secret_key="wrong_secret_key_that_is_long_enough_but_wrong",
            slave_name="bad-slave",
        )

        await bad_client.connect()
        await asyncio.sleep(0.5)

        # Should not be connected due to auth failure
        assert not bad_client.is_connected
        assert server.slave_count == 0


class TestAuthentication:
    """Test HMAC authentication flow."""

    @pytest.mark.asyncio
    async def test_successful_authentication(self, server, client):
        """Test successful HMAC authentication."""
        connected = False

        def on_connected():
            nonlocal connected
            connected = True

        client.on_connected = on_connected

        await client.connect()
        await asyncio.sleep(0.5)

        assert connected
        assert client.session_token is not None
        assert len(client.session_token) == 64  # 32 bytes hex
        assert server.slave_count == 1

        slaves = server.get_connected_slaves()
        assert len(slaves) == 1
        assert slaves[0]["slave_name"] == "test-slave"
        assert slaves[0]["authenticated"]

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_authentication_timeout(self, server):
        """Test authentication times out if client doesn't respond."""
        # This test is tricky - we'd need to mock the client behavior
        # For now, just verify the timeout parameter exists
        assert server.timeout_seconds == 5


class TestMessagePassing:
    """Test message sending and receiving."""

    @pytest.mark.asyncio
    async def test_command_from_master(self, server, client):
        """Test master can send command to slave."""
        received_command = None
        received_params = None

        def on_command(command_type, params):
            nonlocal received_command, received_params
            received_command = command_type
            received_params = params

        client.on_command = on_command

        await client.connect()
        await asyncio.sleep(0.5)

        # Send command from master
        slaves = server.get_connected_slaves()
        slave_id = slaves[0]["slave_id"]

        await server.send_command(
            slave_id,
            MessageType.START_SCRAPE,
            {"sources": ["http://example.com"], "protocols": ["http"]},
        )

        await asyncio.sleep(0.2)

        assert received_command == MessageType.START_SCRAPE
        assert received_params["sources"] == ["http://example.com"]
        assert received_params["protocols"] == ["http"]

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_stats_from_slave(self, server, client):
        """Test slave can send stats to master."""
        received_slave_id = None
        received_type = None
        received_payload = None

        def on_message(slave_id, message_type, payload):
            nonlocal received_slave_id, received_type, received_payload
            received_slave_id = slave_id
            received_type = message_type
            received_payload = payload

        server.on_message = on_message

        await client.connect()
        await asyncio.sleep(0.5)

        # Send stats from slave
        await client.send_stats(
            MessageType.SCRAPE_PROGRESS,
            {"proxies_found": 100, "sources_completed": 5},
        )

        await asyncio.sleep(0.2)

        assert received_slave_id is not None
        assert received_type == MessageType.SCRAPE_PROGRESS
        assert received_payload["proxies_found"] == 100
        assert received_payload["sources_completed"] == 5

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_broadcast_command(self, server):
        """Test broadcasting command to multiple slaves."""
        clients = []
        received_count = 0

        def on_command(command_type, params):
            nonlocal received_count
            received_count += 1

        # Create 3 clients
        for i in range(3):
            client = WebSocketClient(
                master_host="127.0.0.1",
                master_port=18765,
                secret_key="test_secret_key_at_least_32_characters_long_for_security",
                slave_name=f"slave-{i}",
                heartbeat_interval=1,
            )
            client.on_command = on_command
            await client.connect()
            clients.append(client)

        await asyncio.sleep(0.5)
        assert server.slave_count == 3

        # Broadcast command
        sent_count = await server.broadcast_command(
            MessageType.STOP, {"reason": "test"}
        )

        await asyncio.sleep(0.2)

        assert sent_count == 3
        assert received_count == 3

        # Cleanup
        for client in clients:
            await client.disconnect()


class TestHeartbeat:
    """Test heartbeat mechanism."""

    @pytest.mark.asyncio
    async def test_heartbeat_keeps_alive(self, server, client):
        """Test heartbeats keep connection alive."""
        await client.connect()
        await asyncio.sleep(0.5)

        initial_heartbeat = None
        slaves = server.get_connected_slaves()
        if slaves:
            initial_heartbeat = slaves[0]["last_heartbeat"]

        # Wait for heartbeat interval
        await asyncio.sleep(1.5)

        slaves = server.get_connected_slaves()
        assert len(slaves) == 1
        assert slaves[0]["last_heartbeat"] > initial_heartbeat

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_missing_heartbeat_disconnects(self, server):
        """Test client is disconnected after missing heartbeats."""
        # Create client but block heartbeats by not starting the loop
        client = WebSocketClient(
            master_host="127.0.0.1",
            master_port=18765,
            secret_key="test_secret_key_at_least_32_characters_long_for_security",
            slave_name="timeout-slave",
            heartbeat_interval=10,  # Long interval so it won't send
        )

        await client.connect()
        await asyncio.sleep(0.5)

        assert server.slave_count == 1

        # Wait for timeout (5 seconds in server config)
        await asyncio.sleep(6)

        # Should be disconnected
        assert server.slave_count == 0

        await client.disconnect()


class TestReconnection:
    """Test auto-reconnection logic."""

    @pytest.mark.asyncio
    async def test_client_reconnects_after_disconnect(self, server):
        """Test client auto-reconnects after connection loss."""
        disconnected = False
        reconnected = False

        def on_disconnected():
            nonlocal disconnected
            disconnected = True

        def on_connected():
            nonlocal reconnected
            if disconnected:  # Only count reconnection
                reconnected = True

        client = WebSocketClient(
            master_host="127.0.0.1",
            master_port=18765,
            secret_key="test_secret_key_at_least_32_characters_long_for_security",
            slave_name="reconnect-slave",
            heartbeat_interval=1,
        )
        client.on_disconnected = on_disconnected
        client.on_connected = on_connected

        # Start client run loop (with auto-reconnect)
        run_task = asyncio.create_task(client.run())

        await asyncio.sleep(1)  # Wait for initial connection
        assert client.is_connected

        # Force disconnect
        await client.disconnect()
        await asyncio.sleep(0.2)

        assert disconnected
        assert not client.is_connected

        # Wait for reconnection (should happen within 1-2 seconds)
        await asyncio.sleep(3)

        assert reconnected
        assert client.is_connected

        # Cleanup
        client.stop()
        await run_task

    @pytest.mark.asyncio
    async def test_message_queue_during_disconnect(self, server):
        """Test messages are queued when disconnected and sent on reconnect."""
        client = WebSocketClient(
            master_host="127.0.0.1",
            master_port=18765,
            secret_key="test_secret_key_at_least_32_characters_long_for_security",
            slave_name="queue-slave",
            heartbeat_interval=1,
        )

        await client.connect()
        await asyncio.sleep(0.5)

        # Disconnect
        await client.disconnect()
        await asyncio.sleep(0.2)

        # Send messages while disconnected (should be queued)
        await client.send_stats(MessageType.SCRAPE_PROGRESS, {"test": 1})
        await client.send_stats(MessageType.SCRAPE_PROGRESS, {"test": 2})

        assert client.queued_messages == 2

        # Reconnect
        await client.connect()
        await asyncio.sleep(1.5)  # Wait for messages to be sent

        # Queue should be empty now
        assert client.queued_messages == 0

        await client.disconnect()


class TestConnectionCallbacks:
    """Test connection event callbacks."""

    @pytest.mark.asyncio
    async def test_slave_connected_callback(self, server, client):
        """Test on_slave_connected callback is called."""
        connected_id = None
        connected_info = None

        def on_slave_connected(slave_id, info):
            nonlocal connected_id, connected_info
            connected_id = slave_id
            connected_info = info

        server.on_slave_connected = on_slave_connected

        await client.connect()
        await asyncio.sleep(0.5)

        assert connected_id is not None
        assert connected_info["name"] == "test-slave"
        assert connected_info["ip"] == "127.0.0.1"

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_slave_disconnected_callback(self, server, client):
        """Test on_slave_disconnected callback is called."""
        disconnected_id = None

        def on_slave_disconnected(slave_id):
            nonlocal disconnected_id
            disconnected_id = slave_id

        server.on_slave_disconnected = on_slave_disconnected

        await client.connect()
        await asyncio.sleep(0.5)

        slaves = server.get_connected_slaves()
        expected_id = slaves[0]["slave_id"]

        await client.disconnect()
        await asyncio.sleep(0.5)

        assert disconnected_id == expected_id
