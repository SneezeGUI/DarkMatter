import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum

from aiohttp import WSMsgType, web


class ClientType(Enum):
    """Type of connected client."""
    CONTROLLER = "controller"
    AGENT = "agent"


class MessageType(Enum):
    """WebSocket message types."""
    # Authentication
    AUTH_CHALLENGE = "auth_challenge"
    AUTH_RESPONSE = "auth_response"
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"

    # Connection Status
    AGENT_CONNECTED = "agent_connected"
    AGENT_DISCONNECTED = "agent_disconnected"
    AGENT_LIST = "agent_list"

    # Routing
    COMMAND = "command"        # Controller -> Agent(s)
    RESULT = "result"          # Agent -> Controller
    HEARTBEAT = "heartbeat"
    HEARTBEAT_ACK = "heartbeat_ack"


@dataclass
class ConnectedClient:
    """Represents a connected client (Controller or Agent)."""
    client_id: str
    client_type: ClientType
    websocket: web.WebSocketResponse
    name: str = "Unknown"
    ip_address: str = "0.0.0.0"
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    session_token: str | None = None
    extra_info: dict = field(default_factory=dict)

    def __hash__(self):
        return hash(self.client_id)

    def __eq__(self, other):
        if isinstance(other, ConnectedClient):
            return self.client_id == other.client_id
        return False


class RelayServer:
    """
    WebSocket Relay Server.

    Manages connections from Controllers and Agents.
    Routes commands from Controllers to Agents.
    Routes results from Agents to Controllers.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        secret_key: str = "",
        heartbeat_interval: int = 30,
        timeout_seconds: int = 60,
        on_log: callable | None = None,
        on_agent_connected: callable | None = None,
        on_agent_disconnected: callable | None = None,
    ):
        if not secret_key or len(secret_key) < 32:
            raise ValueError("secret_key must be at least 32 characters")

        self.host = host
        self.port = port
        self.secret_key = secret_key.encode()
        self.heartbeat_interval = heartbeat_interval
        self.timeout_seconds = timeout_seconds

        # Callbacks
        self.on_log = on_log
        self.on_agent_connected = on_agent_connected
        self.on_agent_disconnected = on_agent_disconnected

        # State
        self.controllers: dict[str, ConnectedClient] = {}  # controller_id -> client
        self.agents: dict[str, ConnectedClient] = {}  # agent_id -> client
        self.app: web.Application | None = None
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self._running = False
        self._heartbeat_task: asyncio.Task | None = None

        self.logger = logging.getLogger(__name__)

    def _log(self, message: str, level: int = logging.INFO):
        """Log message and trigger callback."""
        self.logger.log(level, message)
        if self.on_log:
            try:
                self.on_log(message)
            except Exception:
                pass

    async def start(self):
        """Start the Relay Server."""
        if self._running:
            return

        self._log(f"Starting Relay Server on {self.host}:{self.port}")

        self.app = web.Application()
        self.app.router.add_get("/ws", self._handle_websocket)

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()

        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_monitor())
        self._log(f"Relay Server running on ws://{self.host}:{self.port}/ws")

    async def stop(self):
        """Stop the Relay Server."""
        if not self._running:
            return

        self._log("Stopping Relay Server...")
        self._running = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # Close all connections
        disconnect_tasks = []
        for client in list(self.controllers.values()):
            disconnect_tasks.append(client.websocket.close(code=1001, message=b"Server shutdown"))
        for client in list(self.agents.values()):
            disconnect_tasks.append(client.websocket.close(code=1001, message=b"Server shutdown"))

        if disconnect_tasks:
            await asyncio.gather(*disconnect_tasks, return_exceptions=True)

        self.controllers.clear()
        self.agents.clear()

        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

        self._log("Relay Server stopped")

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle incoming WebSocket connection."""
        ws = web.WebSocketResponse(heartbeat=self.heartbeat_interval)
        await ws.prepare(request)

        ip_address = request.remote or "unknown"
        temp_id = secrets.token_hex(8)

        self._log(f"New connection from {ip_address} (id: {temp_id})")

        client: ConnectedClient | None = None

        try:
            # Authenticate
            client = await self._authenticate(ws, ip_address, temp_id)
            if not client:
                await ws.close(code=4003, message=b"Authentication failed")
                return ws

            # Register client
            if client.client_type == ClientType.CONTROLLER:
                self.controllers[client.client_id] = client
                self._log(f"Controller connected: {client.name} ({client.client_id})")
                # Send current agent list to new controller
                await self._send_agent_list(client)
            else:
                self.agents[client.client_id] = client
                self._log(f"Agent connected: {client.name} ({client.client_id})")
                # Notify controllers
                await self._notify_controllers_agent_update(client, connected=True)
                if self.on_agent_connected:
                    self.on_agent_connected(client)

            # Message Loop
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._handle_message(client, msg.data)
                elif msg.type == WSMsgType.ERROR:
                    self._log(f"WebSocket error from {client.name}: {ws.exception()}", logging.ERROR)
                    break

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._log(f"Error handling client {temp_id}: {str(e)}", logging.ERROR)
        finally:
            if client:
                await self._disconnect_client(client)
            else:
                await ws.close()

        return ws

    async def _authenticate(self, ws: web.WebSocketResponse, ip_address: str, temp_id: str) -> ConnectedClient | None:
        """Perform HMAC-SHA256 challenge-response authentication."""
        challenge = secrets.token_hex(32)

        try:
            # Send Challenge
            await ws.send_json({
                "type": MessageType.AUTH_CHALLENGE.value,
                "challenge": challenge
            })

            # Wait for Response
            msg = await ws.receive(timeout=10.0)
            if msg.type != WSMsgType.TEXT:
                return None

            data = json.loads(msg.data)

            # Validate structure
            if data.get("type") != MessageType.AUTH_RESPONSE.value:
                return None

            payload = data.get("payload", {})
            response_hmac = payload.get("response")
            client_type_str = payload.get("client_type", "").lower()
            client_name = payload.get("name", f"Client-{temp_id}")
            client_id = payload.get("id", temp_id) # Clients can suggest an ID (e.g. persistent agent ID)

            # Validate HMAC
            expected_hmac = hmac.new(
                self.secret_key,
                challenge.encode(),
                hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(response_hmac or "", expected_hmac):
                self._log(f"Auth failed for {ip_address}: Invalid HMAC")
                await ws.send_json({"type": MessageType.AUTH_FAILURE.value, "reason": "Invalid credentials"})
                return None

            # Determine Client Type
            try:
                client_type = ClientType(client_type_str)
            except ValueError:
                self._log(f"Auth failed for {ip_address}: Invalid client type '{client_type_str}'")
                await ws.send_json({"type": MessageType.AUTH_FAILURE.value, "reason": "Invalid client type"})
                return None

            # Success
            session_token = secrets.token_hex(32)
            await ws.send_json({
                "type": MessageType.AUTH_SUCCESS.value,
                "session_token": session_token
            })

            return ConnectedClient(
                client_id=client_id,
                client_type=client_type,
                websocket=ws,
                name=client_name,
                ip_address=ip_address,
                session_token=session_token,
                extra_info=payload.get("extra_info", {})
            )

        except (json.JSONDecodeError, asyncio.TimeoutError) as e:
            self._log(f"Auth error for {ip_address}: {str(e)}")
            return None
        except Exception as e:
            self._log(f"Auth exception for {ip_address}: {str(e)}", logging.ERROR)
            return None

    async def _handle_message(self, client: ConnectedClient, data: str):
        """Route incoming messages based on client type."""
        try:
            message = json.loads(data)
            msg_type = message.get("type")
            payload = message.get("payload", {})

            # Heartbeat
            if msg_type == MessageType.HEARTBEAT.value:
                client.last_heartbeat = time.time()
                await client.websocket.send_json({
                    "type": MessageType.HEARTBEAT_ACK.value,
                    "timestamp": time.time()
                })
                return

            # Routing Logic
            if client.client_type == ClientType.CONTROLLER:
                await self._route_from_controller(client, msg_type, payload)
            elif client.client_type == ClientType.AGENT:
                await self._route_from_agent(client, msg_type, payload)

        except json.JSONDecodeError:
            pass
        except Exception as e:
            self._log(f"Error processing message from {client.name}: {str(e)}", logging.ERROR)

    async def _route_from_controller(self, controller: ConnectedClient, msg_type: str, payload: dict):
        """Route commands from Controller to Agent(s)."""
        target_agent_id = payload.get("target_agent_id")

        # Construct message to forward
        forward_msg = {
            "type": msg_type,
            "payload": payload,
            "source_controller": controller.client_id,
            "timestamp": time.time()
        }

        if target_agent_id:
            # Unicast
            agent = self.agents.get(target_agent_id)
            if agent:
                await self._send_json_safe(agent, forward_msg)
            else:
                # Notify controller that agent is missing
                await self._send_json_safe(controller, {
                    "type": "error",
                    "payload": {"message": f"Agent {target_agent_id} not found"}
                })
        else:
            # Broadcast
            tasks = []
            for agent in self.agents.values():
                tasks.append(self._send_json_safe(agent, forward_msg))
            if tasks:
                await asyncio.gather(*tasks)

    async def _route_from_agent(self, agent: ConnectedClient, msg_type: str, payload: dict):
        """Route results/stats from Agent to All Controllers."""
        # Annotate with source agent info
        forward_msg = {
            "type": msg_type,
            "payload": payload,
            "source_agent_id": agent.client_id,
            "source_agent_name": agent.name,
            "timestamp": time.time()
        }

        tasks = []
        for controller in self.controllers.values():
            tasks.append(self._send_json_safe(controller, forward_msg))

        if tasks:
            await asyncio.gather(*tasks)

    async def _disconnect_client(self, client: ConnectedClient):
        """Cleanup disconnected client."""
        if client.client_type == ClientType.CONTROLLER:
            if client.client_id in self.controllers:
                del self.controllers[client.client_id]
                self._log(f"Controller disconnected: {client.name}")
        else:
            if client.client_id in self.agents:
                del self.agents[client.client_id]
                self._log(f"Agent disconnected: {client.name}")
                await self._notify_controllers_agent_update(client, connected=False)
                if self.on_agent_disconnected:
                    self.on_agent_disconnected(client)

    async def _notify_controllers_agent_update(self, agent: ConnectedClient, connected: bool):
        """Inform controllers about agent connection changes."""
        msg_type = MessageType.AGENT_CONNECTED.value if connected else MessageType.AGENT_DISCONNECTED.value
        msg = {
            "type": msg_type,
            "payload": {
                "agent_id": agent.client_id,
                "name": agent.name,
                "ip": agent.ip_address,
                "connected_at": agent.connected_at,
                "status": "online" if connected else "offline"
            }
        }

        tasks = [self._send_json_safe(c, msg) for c in self.controllers.values()]
        if tasks:
            await asyncio.gather(*tasks)

    async def _send_agent_list(self, controller: ConnectedClient):
        """Send list of all connected agents to a specific controller."""
        agents_list = [
            {
                "agent_id": a.client_id,
                "name": a.name,
                "ip": a.ip_address,
                "connected_at": a.connected_at,
                "status": "online"
            }
            for a in self.agents.values()
        ]

        await self._send_json_safe(controller, {
            "type": MessageType.AGENT_LIST.value,
            "payload": {"agents": agents_list}
        })

    async def _send_json_safe(self, client: ConnectedClient, data: dict):
        """Safely send JSON message to client."""
        try:
            await client.websocket.send_json(data)
        except Exception as e:
            self._log(f"Failed to send to {client.name}: {str(e)}", logging.DEBUG)

    async def _heartbeat_monitor(self):
        """Check for silent disconnections."""
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                now = time.time()

                # Check Agents
                timed_out_agents = [
                    a for a in self.agents.values()
                    if now - a.last_heartbeat > self.timeout_seconds
                ]
                for agent in timed_out_agents:
                    self._log(f"Agent timeout: {agent.name}")
                    await agent.websocket.close(code=1000, message=b"Heartbeat timeout")
                    # _disconnect_client will be called by the handler loop exiting

                # Check Controllers
                timed_out_controllers = [
                    c for c in self.controllers.values()
                    if now - c.last_heartbeat > self.timeout_seconds
                ]
                for controller in timed_out_controllers:
                    self._log(f"Controller timeout: {controller.name}")
                    await controller.websocket.close(code=1000, message=b"Heartbeat timeout")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log(f"Heartbeat monitor error: {str(e)}", logging.ERROR)
                await asyncio.sleep(5)

    def get_agents(self) -> list[dict]:
        """Get public info of all connected agents."""
        return [
            {
                "id": agent.client_id,
                "name": agent.name,
                "ip": agent.ip_address,
                "connected_at": agent.connected_at
            }
            for agent in self.agents.values()
        ]
