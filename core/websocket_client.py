"""
WebSocket Client for Slave/Master Communication.

Provides WebSocket client with auto-reconnect, HMAC authentication,
message queuing, and heartbeat support for slave nodes.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from collections import deque
from collections.abc import Callable

import aiohttp

from .websocket_server import MessageType


class WebSocketClient:
    """
    WebSocket client for Slave/Master communication.

    Features:
    - Auto-reconnect with exponential backoff
    - HMAC authentication
    - Message queue for offline resilience
    - Automatic heartbeat
    - Command dispatcher
    - Support for Direct, Relay, and Cloudflare modes
    """

    def __init__(
        self,
        master_host: str,
        master_port: int,
        secret_key: str,
        slave_name: str = "slave",
        heartbeat_interval: int = 30,
        max_queue_size: int = 1000,
        on_command: Callable | None = None,
        on_connected: Callable | None = None,
        on_disconnected: Callable | None = None,
        connection_mode: str = "direct",
        client_id: str | None = None,
    ):
        """
        Initialize WebSocket client.

        Args:
            master_host: Master/Relay server hostname/IP (or Cloudflare URL)
            master_port: Master/Relay server port (ignored for Cloudflare)
            secret_key: Shared secret for HMAC authentication
            slave_name: Name of this slave node
            heartbeat_interval: Heartbeat interval in seconds
            max_queue_size: Maximum queued messages when offline
            on_command: Callback for commands (command_type, params)
            on_connected: Callback when connected to master
            on_disconnected: Callback when disconnected from master
            connection_mode: "direct", "relay", or "cloudflare"
            client_id: Optional persistent client ID (for relay mode)
        """
        if not secret_key or len(secret_key) < 32:
            raise ValueError("secret_key must be at least 32 characters")

        self.connection_mode = connection_mode.lower()
        self.client_id = client_id

        # Build URL based on mode
        if self.connection_mode == "cloudflare":
            # master_host is the full Cloudflare URL (e.g., wss://tunnel.example.com)
            if master_host.startswith(("ws://", "wss://")):
                self.master_url = master_host.rstrip("/") + "/ws"
            else:
                self.master_url = f"wss://{master_host}/ws"
        else:
            self.master_url = f"ws://{master_host}:{master_port}/ws"

        self.secret_key = secret_key.encode()
        self.slave_name = slave_name
        self.heartbeat_interval = heartbeat_interval
        self.max_queue_size = max_queue_size

        # Callbacks
        self.on_command = on_command
        self.on_connected = on_connected
        self.on_disconnected = on_disconnected

        # State
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self.session: aiohttp.ClientSession | None = None
        self.session_token: str | None = None
        self.connected = False
        self._running = False

        # Message queue for offline resilience
        self.message_queue: deque = deque(maxlen=max_queue_size)

        # Tasks
        self._heartbeat_task: asyncio.Task | None = None
        self._receiver_task: asyncio.Task | None = None
        self._sender_task: asyncio.Task | None = None

        # Reconnection parameters
        self.reconnect_delay = 1  # Initial delay
        self.max_reconnect_delay = 60  # Max delay

        self.logger = logging.getLogger(__name__)

    async def connect(self):
        """Connect to master server with authentication."""
        if self.connected:
            self.logger.warning("Already connected")
            return

        try:
            self.logger.info(f"Connecting to master at {self.master_url}")

            # Create session
            if not self.session:
                self.session = aiohttp.ClientSession()

            # Connect WebSocket
            self.ws = await self.session.ws_connect(
                self.master_url, heartbeat=self.heartbeat_interval
            )

            # Authenticate
            if not await self._authenticate():
                await self.disconnect()
                return

            self.connected = True
            self.reconnect_delay = 1  # Reset backoff on successful connection

            self.logger.info(f"Connected to master as {self.slave_name}")

            # Notify connection
            if self.on_connected:
                self.on_connected()

            # Start background tasks
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self._receiver_task = asyncio.create_task(self._receiver_loop())
            self._sender_task = asyncio.create_task(self._sender_loop())

        except aiohttp.ClientError as e:
            self.logger.error(f"Connection error: {e}")
            await self.disconnect()
        except Exception as e:
            self.logger.error(f"Unexpected error during connection: {e}", exc_info=True)
            await self.disconnect()

    async def disconnect(self):
        """Disconnect from master server."""
        if not self.connected:
            return

        self.logger.info("Disconnecting from master")
        self.connected = False

        # Cancel tasks
        for task in [self._heartbeat_task, self._receiver_task, self._sender_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Close WebSocket
        if self.ws:
            await self.ws.close()
            self.ws = None

        # Notify disconnection
        if self.on_disconnected:
            self.on_disconnected()

    async def run(self):
        """Run client with auto-reconnect."""
        self._running = True

        while self._running:
            try:
                await self.connect()

                # Wait for disconnection
                while self.connected and self._running:
                    await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in run loop: {e}", exc_info=True)

            # Exponential backoff
            if self._running and not self.connected:
                self.logger.info(
                    f"Reconnecting in {self.reconnect_delay}s..."
                )
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(
                    self.reconnect_delay * 2, self.max_reconnect_delay
                )

        # Final cleanup
        await self.disconnect()

        if self.session:
            await self.session.close()
            self.session = None

    def stop(self):
        """Stop the client."""
        self._running = False

    async def _authenticate(self) -> bool:
        """
        Authenticate with master/relay using HMAC challenge-response.

        Supports both direct mode (to MasterServer) and relay mode (to RelayServer).
        """
        try:
            # Wait for challenge
            msg = await asyncio.wait_for(self.ws.receive(), timeout=10.0)

            if msg.type != aiohttp.WSMsgType.TEXT:
                self.logger.error(f"Expected text message, got {msg.type}")
                return False

            data = json.loads(msg.data)

            if data.get("type") != MessageType.AUTH_CHALLENGE.value:
                self.logger.error(f"Expected auth_challenge, got {data.get('type')}")
                return False

            # Get challenge - relay server sends it directly, master wraps in payload
            challenge = data.get("challenge") or data.get("payload", {}).get("challenge")
            if not challenge:
                self.logger.error("No challenge in auth_challenge")
                return False

            # Compute HMAC
            response_hmac = hmac.new(
                self.secret_key, challenge.encode(), hashlib.sha256
            ).hexdigest()

            # Build auth response based on mode
            if self.connection_mode == "relay":
                # Relay server expects different payload structure
                auth_payload = {
                    "response": response_hmac,
                    "client_type": "agent",
                    "name": self.slave_name,
                    "id": self.client_id or self.slave_name,
                }
            else:
                # Direct mode - original MasterServer format
                auth_payload = {
                    "hmac": response_hmac,
                    "slave_name": self.slave_name,
                }

            # Send response
            await self._send_message(MessageType.AUTH_RESPONSE, auth_payload)

            # Wait for auth result
            msg = await asyncio.wait_for(self.ws.receive(), timeout=10.0)

            if msg.type != aiohttp.WSMsgType.TEXT:
                self.logger.error(f"Expected text message, got {msg.type}")
                return False

            data = json.loads(msg.data)
            msg_type = data.get("type")

            if msg_type == MessageType.AUTH_SUCCESS.value:
                # Session token can be in payload or directly in data
                self.session_token = (
                    data.get("session_token") or
                    data.get("payload", {}).get("session_token")
                )
                self.logger.info(f"Authentication successful ({self.connection_mode} mode)")
                return True
            elif msg_type == MessageType.AUTH_FAILURE.value:
                reason = data.get("reason") or data.get("payload", {}).get("reason", "Unknown")
                self.logger.error(f"Authentication failed: {reason}")
                return False
            else:
                self.logger.error(f"Unexpected auth response: {msg_type}")
                return False

        except asyncio.TimeoutError:
            self.logger.error("Authentication timeout")
            return False
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON during auth: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Authentication error: {e}", exc_info=True)
            return False

    async def _send_message(self, message_type: MessageType, payload: dict):
        """Send message to master."""
        message = {
            "type": message_type.value,
            "timestamp": time.time(),
            "payload": payload,
        }

        if self.session_token:
            message["session_token"] = self.session_token

        try:
            await self.ws.send_json(message)
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
            self.connected = False

    async def send_stats(self, stats_type: MessageType, stats: dict):
        """
        Send stats update to master.

        If not connected, message is queued for later delivery.
        """
        if self.connected:
            await self._send_message(stats_type, stats)
        else:
            # Queue for later
            if len(self.message_queue) < self.max_queue_size:
                self.message_queue.append((stats_type, stats))
            else:
                self.logger.warning("Message queue full, dropping message")

    async def send_log(self, level: str, message: str):
        """Send log message to master."""
        log_type = {
            "info": MessageType.LOG_INFO,
            "warning": MessageType.LOG_WARNING,
            "error": MessageType.LOG_ERROR,
        }.get(level.lower(), MessageType.LOG_INFO)

        await self.send_stats(log_type, {"message": message, "timestamp": time.time()})

    async def _heartbeat_loop(self):
        """Send periodic heartbeats to master."""
        self.logger.info("Heartbeat loop started")

        try:
            while self.connected:
                await asyncio.sleep(self.heartbeat_interval)

                if not self.connected:
                    break

                await self._send_message(MessageType.HEARTBEAT, {})

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Heartbeat loop error: {e}", exc_info=True)
            self.connected = False

        self.logger.info("Heartbeat loop stopped")

    async def _receiver_loop(self):
        """Receive messages from master."""
        self.logger.info("Receiver loop started")

        try:
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.logger.error(f"WebSocket error: {self.ws.exception()}")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    self.logger.info("WebSocket closed by server")
                    break

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Receiver loop error: {e}", exc_info=True)
        finally:
            self.connected = False

        self.logger.info("Receiver loop stopped")

    async def _sender_loop(self):
        """Send queued messages when connection is restored."""
        self.logger.info("Sender loop started")

        try:
            while self.connected:
                await asyncio.sleep(1)

                # Send queued messages
                while self.message_queue and self.connected:
                    message_type, payload = self.message_queue.popleft()
                    await self._send_message(message_type, payload)
                    await asyncio.sleep(0.1)  # Rate limit

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Sender loop error: {e}", exc_info=True)

        self.logger.info("Sender loop stopped")

    async def _handle_message(self, data: str):
        """Handle incoming message from master."""
        try:
            message = json.loads(data)
            msg_type = message.get("type")
            payload = message.get("payload", {})

            # Handle heartbeat ack
            if msg_type == MessageType.HEARTBEAT_ACK.value:
                return

            # Dispatch command
            if self.on_command:
                try:
                    message_type = MessageType(msg_type)
                    self.on_command(message_type, payload)
                except ValueError:
                    self.logger.warning(f"Unknown message type: {msg_type}")

        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON from master: {e}")
        except Exception as e:
            self.logger.error(f"Error handling message: {e}", exc_info=True)

    @property
    def is_connected(self) -> bool:
        """Check if connected to master."""
        return self.connected

    @property
    def queued_messages(self) -> int:
        """Get number of queued messages."""
        return len(self.message_queue)
