"""
WebSocket Server for Master/Slave Communication.

Provides secure WebSocket server with HMAC authentication, connection management,
message routing, and heartbeat monitoring for distributed traffic generation.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import aiohttp
from aiohttp import web


class MessageType(Enum):
    """WebSocket message types."""

    # Authentication
    AUTH_CHALLENGE = "auth_challenge"
    AUTH_RESPONSE = "auth_response"
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"

    # Commands (Master → Slave)
    START_SCRAPE = "start_scrape"
    START_CHECK = "start_check"
    START_TRAFFIC = "start_traffic"
    START_SCAN = "start_scan"
    STOP = "stop"
    GET_STATUS = "get_status"
    UPDATE_CONFIG = "update_config"

    # Stats (Slave → Master)
    SCRAPE_PROGRESS = "scrape_progress"
    CHECK_PROGRESS = "check_progress"
    TRAFFIC_STATS = "traffic_stats"
    SCAN_RESULTS = "scan_results"
    STATUS_UPDATE = "status_update"

    # Logs (Slave → Master)
    LOG_INFO = "log_info"
    LOG_WARNING = "log_warning"
    LOG_ERROR = "log_error"

    # Heartbeat
    HEARTBEAT = "heartbeat"
    HEARTBEAT_ACK = "heartbeat_ack"


@dataclass
class SlaveConnection:
    """Represents a connected slave."""

    slave_id: str
    websocket: web.WebSocketResponse
    authenticated: bool = False
    session_token: Optional[str] = None
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    ip_address: str = ""
    slave_name: str = ""


class WebSocketServer:
    """
    WebSocket server for Master/Slave communication.

    Features:
    - HMAC-SHA256 authentication
    - Connection management with heartbeat monitoring
    - Message routing with type validation
    - Session token management
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        secret_key: str = "",
        heartbeat_interval: int = 30,
        timeout_seconds: int = 60,
        on_message: Optional[Callable] = None,
        on_slave_connected: Optional[Callable] = None,
        on_slave_disconnected: Optional[Callable] = None,
    ):
        """
        Initialize WebSocket server.

        Args:
            host: Server bind address
            port: Server port
            secret_key: Shared secret for HMAC authentication (64 chars recommended)
            heartbeat_interval: Heartbeat interval in seconds
            timeout_seconds: Connection timeout after missed heartbeats
            on_message: Callback for incoming messages (slave_id, message_type, payload)
            on_slave_connected: Callback when slave connects (slave_id, slave_info)
            on_slave_disconnected: Callback when slave disconnects (slave_id)
        """
        if not secret_key or len(secret_key) < 32:
            raise ValueError("secret_key must be at least 32 characters")

        self.host = host
        self.port = port
        self.secret_key = secret_key.encode()
        self.heartbeat_interval = heartbeat_interval
        self.timeout_seconds = timeout_seconds

        # Callbacks
        self.on_message = on_message
        self.on_slave_connected = on_slave_connected
        self.on_slave_disconnected = on_slave_disconnected

        # State
        self.slaves: dict[str, SlaveConnection] = {}
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self._running = False
        self._heartbeat_task: Optional[asyncio.Task] = None

        self.logger = logging.getLogger(__name__)

    async def start(self):
        """Start the WebSocket server."""
        if self._running:
            self.logger.warning("Server already running")
            return

        self.logger.info(f"Starting WebSocket server on {self.host}:{self.port}")

        # Create aiohttp application
        self.app = web.Application()
        self.app.router.add_get("/ws", self._handle_websocket)

        # Start server
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()

        self._running = True

        # Start heartbeat monitor
        self._heartbeat_task = asyncio.create_task(self._heartbeat_monitor())

        self.logger.info(f"WebSocket server started on ws://{self.host}:{self.port}/ws")

    async def stop(self):
        """Stop the WebSocket server."""
        if not self._running:
            return

        self.logger.info("Stopping WebSocket server...")
        self._running = False

        # Cancel heartbeat monitor
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # Close all slave connections
        for slave_id in list(self.slaves.keys()):
            await self._disconnect_slave(slave_id, reason="Server shutdown")

        # Stop server
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

        self.logger.info("WebSocket server stopped")

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle incoming WebSocket connection."""
        ws = web.WebSocketResponse(heartbeat=self.heartbeat_interval)
        await ws.prepare(request)

        slave_id = secrets.token_hex(16)
        ip_address = request.remote or "unknown"

        self.logger.info(f"New connection from {ip_address} (slave_id: {slave_id})")

        # Create slave connection
        slave = SlaveConnection(
            slave_id=slave_id, websocket=ws, ip_address=ip_address
        )
        self.slaves[slave_id] = slave

        try:
            # Authentication flow
            if not await self._authenticate_slave(slave):
                await ws.close()
                return ws

            # Notify connection
            if self.on_slave_connected:
                self.on_slave_connected(slave_id, {
                    "ip": ip_address,
                    "name": slave.slave_name,
                    "connected_at": slave.connected_at,
                })

            # Message loop
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(slave, msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.logger.error(
                        f"WebSocket error from {slave_id}: {ws.exception()}"
                    )
                    break

        except asyncio.CancelledError:
            self.logger.info(f"Connection cancelled for {slave_id}")
        except Exception as e:
            self.logger.error(f"Error handling {slave_id}: {e}", exc_info=True)
        finally:
            await self._disconnect_slave(slave_id)

        return ws

    async def _authenticate_slave(self, slave: SlaveConnection) -> bool:
        """
        Authenticate slave using HMAC challenge-response.

        Flow:
        1. Server sends challenge (random nonce)
        2. Slave responds with HMAC(secret + challenge)
        3. Server validates response
        4. Server issues session token
        """
        # Generate challenge
        challenge = secrets.token_hex(32)

        # Send challenge
        await self._send_message(
            slave.websocket,
            MessageType.AUTH_CHALLENGE,
            {"challenge": challenge},
        )

        # Wait for response (10 second timeout)
        try:
            msg = await asyncio.wait_for(slave.websocket.receive(), timeout=10.0)

            if msg.type != aiohttp.WSMsgType.TEXT:
                self.logger.warning(f"Expected text message, got {msg.type}")
                return False

            data = json.loads(msg.data)

            if data.get("type") != MessageType.AUTH_RESPONSE.value:
                self.logger.warning(f"Expected auth_response, got {data.get('type')}")
                return False

            # Validate HMAC
            slave_hmac = data.get("payload", {}).get("hmac", "")
            slave_name = data.get("payload", {}).get("slave_name", "Unknown")

            expected_hmac = hmac.new(
                self.secret_key, challenge.encode(), hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(slave_hmac, expected_hmac):
                self.logger.warning(f"Authentication failed for {slave.slave_id}")
                await self._send_message(
                    slave.websocket,
                    MessageType.AUTH_FAILURE,
                    {"reason": "Invalid credentials"},
                )
                return False

            # Authentication successful - issue session token
            session_token = secrets.token_hex(32)
            slave.authenticated = True
            slave.session_token = session_token
            slave.slave_name = slave_name

            await self._send_message(
                slave.websocket,
                MessageType.AUTH_SUCCESS,
                {"session_token": session_token},
            )

            self.logger.info(
                f"Slave {slave_name} ({slave.slave_id}) authenticated successfully"
            )
            return True

        except asyncio.TimeoutError:
            self.logger.warning(f"Authentication timeout for {slave.slave_id}")
            return False
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in auth response: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Authentication error: {e}", exc_info=True)
            return False

    async def _handle_message(self, slave: SlaveConnection, data: str):
        """Handle incoming message from slave."""
        try:
            message = json.loads(data)
            msg_type = message.get("type")
            payload = message.get("payload", {})
            timestamp = message.get("timestamp", time.time())

            # Validate session token
            token = message.get("session_token")
            if token != slave.session_token:
                self.logger.warning(
                    f"Invalid session token from {slave.slave_id}"
                )
                return

            # Handle heartbeat
            if msg_type == MessageType.HEARTBEAT.value:
                slave.last_heartbeat = time.time()
                await self._send_message(
                    slave.websocket,
                    MessageType.HEARTBEAT_ACK,
                    {"timestamp": time.time()},
                    session_token=slave.session_token,
                )
                return

            # Route message to callback
            if self.on_message:
                try:
                    message_type = MessageType(msg_type)
                    self.on_message(slave.slave_id, message_type, payload)
                except ValueError:
                    self.logger.warning(f"Unknown message type: {msg_type}")

        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON from {slave.slave_id}: {e}")
        except Exception as e:
            self.logger.error(
                f"Error handling message from {slave.slave_id}: {e}", exc_info=True
            )

    async def _send_message(
        self,
        websocket: web.WebSocketResponse,
        message_type: MessageType,
        payload: dict,
        session_token: Optional[str] = None,
    ):
        """Send message to slave."""
        message = {
            "type": message_type.value,
            "timestamp": time.time(),
            "payload": payload,
        }

        if session_token:
            message["session_token"] = session_token

        try:
            await websocket.send_json(message)
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")

    async def send_command(
        self, slave_id: str, command_type: MessageType, params: dict
    ) -> bool:
        """
        Send command to specific slave.

        Returns:
            True if sent successfully, False otherwise
        """
        slave = self.slaves.get(slave_id)
        if not slave or not slave.authenticated:
            self.logger.warning(f"Cannot send command to {slave_id}: not connected")
            return False

        try:
            await self._send_message(
                slave.websocket,
                command_type,
                params,
                session_token=slave.session_token,
            )
            return True
        except Exception as e:
            self.logger.error(f"Error sending command to {slave_id}: {e}")
            return False

    async def broadcast_command(self, command_type: MessageType, params: dict) -> int:
        """
        Broadcast command to all connected slaves.

        Returns:
            Number of slaves that received the command
        """
        count = 0
        for slave_id in list(self.slaves.keys()):
            if await self.send_command(slave_id, command_type, params):
                count += 1
        return count

    async def _heartbeat_monitor(self):
        """Monitor slave heartbeats and disconnect timed-out slaves."""
        self.logger.info("Heartbeat monitor started")

        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)

                current_time = time.time()
                timed_out = []

                for slave_id, slave in self.slaves.items():
                    if not slave.authenticated:
                        continue

                    time_since_heartbeat = current_time - slave.last_heartbeat

                    if time_since_heartbeat > self.timeout_seconds:
                        self.logger.warning(
                            f"Slave {slave_id} timed out ({time_since_heartbeat:.1f}s)"
                        )
                        timed_out.append(slave_id)

                # Disconnect timed out slaves
                for slave_id in timed_out:
                    await self._disconnect_slave(slave_id, reason="Heartbeat timeout")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Heartbeat monitor error: {e}", exc_info=True)

        self.logger.info("Heartbeat monitor stopped")

    async def _disconnect_slave(self, slave_id: str, reason: str = "Disconnected"):
        """Disconnect and clean up slave connection."""
        slave = self.slaves.get(slave_id)
        if not slave:
            return

        self.logger.info(f"Disconnecting slave {slave_id}: {reason}")

        # Close WebSocket
        try:
            await slave.websocket.close()
        except Exception:
            pass

        # Remove from registry
        del self.slaves[slave_id]

        # Notify disconnection
        if self.on_slave_disconnected and slave.authenticated:
            self.on_slave_disconnected(slave_id)

    def get_connected_slaves(self) -> list[dict]:
        """Get list of connected slaves with their info."""
        return [
            {
                "slave_id": slave.slave_id,
                "slave_name": slave.slave_name,
                "ip_address": slave.ip_address,
                "connected_at": slave.connected_at,
                "last_heartbeat": slave.last_heartbeat,
                "authenticated": slave.authenticated,
            }
            for slave in self.slaves.values()
            if slave.authenticated
        ]

    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running

    @property
    def slave_count(self) -> int:
        """Get number of authenticated slaves."""
        return sum(1 for s in self.slaves.values() if s.authenticated)
