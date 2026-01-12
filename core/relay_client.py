"""
Relay Client for Controller/Agent Communication.

Provides WebSocket client for connecting to a RelayServer.
Used by both Controller (GUI) and Agents (slaves) to connect through a relay.
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


class RelayControllerClient:
    """
    WebSocket client for Controller connecting to RelayServer.

    The Controller connects to the relay to:
    - Receive agent connection/disconnection notifications
    - Send commands to agents (broadcast or unicast)
    - Receive results/stats from agents
    """

    def __init__(
        self,
        relay_host: str,
        relay_port: int,
        secret_key: str,
        controller_name: str = "Controller",
        heartbeat_interval: int = 30,
        on_agent_connected: Callable | None = None,
        on_agent_disconnected: Callable | None = None,
        on_agent_message: Callable | None = None,
        on_log: Callable | None = None,
        on_connected: Callable | None = None,
        on_disconnected: Callable | None = None,
        callback_wrapper: Callable | None = None,
    ):
        """
        Initialize relay controller client.

        Args:
            relay_host: Relay server hostname/IP
            relay_port: Relay server port
            secret_key: Shared secret for HMAC authentication
            controller_name: Name for this controller
            heartbeat_interval: Heartbeat interval in seconds
            on_agent_connected: Callback when an agent connects (agent_id, info)
            on_agent_disconnected: Callback when an agent disconnects (agent_id)
            on_agent_message: Callback for messages from agents (agent_id, msg_type, payload)
            on_log: Callback for log messages
            on_connected: Callback when connected to relay
            on_disconnected: Callback when disconnected from relay
            callback_wrapper: Wrapper for GUI-safe callbacks (e.g., app.after)
        """
        if not secret_key or len(secret_key) < 32:
            raise ValueError("secret_key must be at least 32 characters")

        self.relay_url = f"ws://{relay_host}:{relay_port}/ws"
        self.secret_key = secret_key.encode()
        self.controller_name = controller_name
        self.heartbeat_interval = heartbeat_interval

        # Callbacks
        self.on_agent_connected = on_agent_connected
        self.on_agent_disconnected = on_agent_disconnected
        self.on_agent_message = on_agent_message
        self.on_log = on_log
        self.on_connected = on_connected
        self.on_disconnected = on_disconnected
        self.callback_wrapper = callback_wrapper or (lambda cb: cb())

        # State
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self.session: aiohttp.ClientSession | None = None
        self.session_token: str | None = None
        self.connected = False
        self._running = False

        # Connected agents cache
        self.agents: dict[str, dict] = {}

        # Message queue for offline resilience
        self.message_queue: deque = deque(maxlen=1000)

        # Tasks
        self._heartbeat_task: asyncio.Task | None = None
        self._receiver_task: asyncio.Task | None = None
        self._run_task: asyncio.Task | None = None

        # Reconnection parameters
        self.reconnect_delay = 1
        self.max_reconnect_delay = 60

        # Stop event for clean shutdown
        self._stop_event: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        self.logger = logging.getLogger(__name__)

    def _log(self, message: str):
        """Log message and invoke callback."""
        self.logger.info(message)
        if self.on_log:
            self.callback_wrapper(lambda: self.on_log(message))

    async def connect(self):
        """Connect to relay server with authentication."""
        if self.connected:
            self._log("Already connected to relay")
            return

        try:
            self._log(f"Connecting to relay at {self.relay_url}")

            # Create session
            if not self.session:
                self.session = aiohttp.ClientSession()

            # Connect WebSocket
            self.ws = await self.session.ws_connect(
                self.relay_url, heartbeat=self.heartbeat_interval
            )

            # Authenticate
            if not await self._authenticate():
                await self.disconnect()
                return

            self.connected = True
            self.reconnect_delay = 1  # Reset backoff

            self._log(f"Connected to relay as controller '{self.controller_name}'")

            # Invoke connected callback
            if self.on_connected:
                self.callback_wrapper(self.on_connected)

            # Start background tasks
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self._receiver_task = asyncio.create_task(self._receiver_loop())

        except aiohttp.ClientError as e:
            self._log(f"Connection error: {e}")
            await self.disconnect()
        except Exception as e:
            self._log(f"Unexpected error during connection: {e}")
            await self.disconnect()

    async def disconnect(self):
        """Disconnect from relay server."""
        if not self.connected and not self.ws:
            return

        was_connected = self.connected
        self._log("Disconnecting from relay")
        self.connected = False

        # Cancel tasks
        for task in [self._heartbeat_task, self._receiver_task]:
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

        # Invoke disconnected callback
        if was_connected and self.on_disconnected:
            self.callback_wrapper(self.on_disconnected)

    async def run(self):
        """Run client with auto-reconnect."""
        self._running = True
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()

        while self._running:
            try:
                await self.connect()

                # Wait for disconnection or stop signal
                while self.connected and self._running:
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=1.0)
                        # Stop event was set
                        break
                    except asyncio.TimeoutError:
                        # Normal timeout, continue loop
                        pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log(f"Error in run loop: {e}")

            # Exponential backoff (interruptible)
            if self._running and not self.connected:
                self._log(f"Reconnecting in {self.reconnect_delay}s...")
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self.reconnect_delay
                    )
                    # Stop event was set during backoff
                    break
                except asyncio.TimeoutError:
                    # Normal timeout, continue to reconnect
                    pass
                self.reconnect_delay = min(
                    self.reconnect_delay * 2, self.max_reconnect_delay
                )

        # Final cleanup
        await self.disconnect()

        if self.session:
            await self.session.close()
            self.session = None

        self._log("Relay client stopped")

    def stop(self):
        """Stop the client (thread-safe)."""
        self._running = False

        # Signal stop event if we have an event loop
        if self._stop_event and self._loop:
            try:
                self._loop.call_soon_threadsafe(self._stop_event.set)
            except RuntimeError:
                # Event loop already closed
                pass

    async def stop_async(self):
        """Stop the client (async version)."""
        self._running = False
        if self._stop_event:
            self._stop_event.set()
        await self.disconnect()

    async def _authenticate(self) -> bool:
        """Authenticate with relay as a controller."""
        try:
            # Wait for challenge
            msg = await asyncio.wait_for(self.ws.receive(), timeout=10.0)

            if msg.type != aiohttp.WSMsgType.TEXT:
                self._log(f"Expected text message, got {msg.type}")
                return False

            data = json.loads(msg.data)

            if data.get("type") != "auth_challenge":
                self._log(f"Expected auth_challenge, got {data.get('type')}")
                return False

            challenge = data.get("challenge")
            if not challenge:
                self._log("No challenge in auth_challenge")
                return False

            # Compute HMAC
            response_hmac = hmac.new(
                self.secret_key, challenge.encode(), hashlib.sha256
            ).hexdigest()

            # Send response with controller type
            await self.ws.send_json({
                "type": "auth_response",
                "payload": {
                    "response": response_hmac,
                    "client_type": "controller",
                    "name": self.controller_name,
                    "id": f"controller-{self.controller_name}",
                }
            })

            # Wait for auth result
            msg = await asyncio.wait_for(self.ws.receive(), timeout=10.0)

            if msg.type != aiohttp.WSMsgType.TEXT:
                self._log(f"Expected text message, got {msg.type}")
                return False

            data = json.loads(msg.data)
            msg_type = data.get("type")

            if msg_type == "auth_success":
                self.session_token = data.get("session_token")
                self._log("Authentication successful")
                return True
            elif msg_type == "auth_failure":
                reason = data.get("reason", "Unknown")
                self._log(f"Authentication failed: {reason}")
                return False
            else:
                self._log(f"Unexpected auth response: {msg_type}")
                return False

        except asyncio.TimeoutError:
            self._log("Authentication timeout")
            return False
        except json.JSONDecodeError as e:
            self._log(f"Invalid JSON during auth: {e}")
            return False
        except Exception as e:
            self._log(f"Authentication error: {e}")
            return False

    async def _heartbeat_loop(self):
        """Send periodic heartbeats to relay."""
        try:
            while self.connected:
                await asyncio.sleep(self.heartbeat_interval)

                if not self.connected:
                    break

                await self.ws.send_json({"type": "heartbeat"})

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._log(f"Heartbeat error: {e}")
            self.connected = False

    async def _receiver_loop(self):
        """Receive messages from relay."""
        self._log("Receiver loop started")
        self._log(f"WebSocket state: closed={self.ws.closed}, close_code={self.ws.close_code}")
        try:
            async for msg in self.ws:
                self._log(f"Received message type: {msg.type}")
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self._log(f"WebSocket error: {self.ws.exception()}")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    self._log(f"WebSocket closed by relay: {msg.extra}")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSE:
                    self._log(f"WebSocket CLOSE frame received: code={msg.data}, reason={msg.extra}")
                    break
            self._log("Receiver loop ended (iteration finished)")

        except asyncio.CancelledError:
            self._log("Receiver loop cancelled")
        except Exception as e:
            self._log(f"Receiver error: {e}")
        finally:
            self._log("Receiver loop finally block - setting connected=False")
            self.connected = False

    async def _handle_message(self, data: str):
        """Handle incoming message from relay."""
        try:
            message = json.loads(data)
            msg_type = message.get("type")
            payload = message.get("payload", {})

            # Handle heartbeat ack
            if msg_type == "heartbeat_ack":
                return

            # Handle agent list (sent on connect)
            if msg_type == "agent_list":
                agents = payload.get("agents", [])
                for agent in agents:
                    agent_id = agent.get("agent_id") or agent.get("id")
                    self.agents[agent_id] = agent
                    if self.on_agent_connected:
                        self.callback_wrapper(
                            lambda a=agent: self.on_agent_connected(
                                a.get("agent_id") or a.get("id"),
                                a
                            )
                        )
                self._log(f"Received agent list: {len(agents)} agents")
                return

            # Handle agent connected
            if msg_type == "agent_connected":
                agent_id = payload.get("agent_id")
                self.agents[agent_id] = payload
                if self.on_agent_connected:
                    self.callback_wrapper(
                        lambda: self.on_agent_connected(agent_id, payload)
                    )
                self._log(f"Agent connected: {payload.get('name', agent_id)}")
                return

            # Handle agent disconnected
            if msg_type == "agent_disconnected":
                agent_id = payload.get("agent_id")
                self.agents.pop(agent_id, None)
                if self.on_agent_disconnected:
                    self.callback_wrapper(
                        lambda: self.on_agent_disconnected(agent_id)
                    )
                self._log(f"Agent disconnected: {payload.get('name', agent_id)}")
                return

            # Handle messages from agents
            source_agent_id = message.get("source_agent_id")
            if source_agent_id and self.on_agent_message:
                self.callback_wrapper(
                    lambda: self.on_agent_message(source_agent_id, msg_type, payload)
                )

        except json.JSONDecodeError as e:
            self._log(f"Invalid JSON from relay: {e}")
        except Exception as e:
            self._log(f"Error handling message: {e}")

    async def send_command(self, command_type: str, payload: dict, target_agent_id: str | None = None):
        """
        Send command to agents via relay.

        Args:
            command_type: Type of command (e.g., "start_scrape", "start_traffic")
            payload: Command parameters
            target_agent_id: Specific agent ID, or None for broadcast
        """
        if not self.connected:
            self._log("Cannot send command: not connected")
            return False

        message = {
            "type": command_type,
            "payload": payload,
            "timestamp": time.time(),
        }

        if target_agent_id:
            message["payload"]["target_agent_id"] = target_agent_id

        try:
            await self.ws.send_json(message)
            return True
        except Exception as e:
            self._log(f"Error sending command: {e}")
            return False

    def send_command_sync(self, command_type: str, payload: dict, target_agent_id: str | None = None):
        """Synchronous wrapper for send_command (schedules on event loop)."""
        if not self.connected:
            return False

        asyncio.create_task(self.send_command(command_type, payload, target_agent_id))
        return True

    def get_agents(self) -> list[dict]:
        """Get list of connected agents."""
        return list(self.agents.values())

    @property
    def agent_count(self) -> int:
        """Get number of connected agents."""
        return len(self.agents)

    @property
    def is_connected(self) -> bool:
        """Check if connected to relay."""
        return self.connected
