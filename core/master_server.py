import asyncio
import contextlib
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from .websocket_server import MessageType, WebSocketServer


@dataclass
class SlaveStats:
    """Statistics for a single slave."""

    slave_id: str
    slave_name: str
    ip_address: str
    connected_at: float
    last_heartbeat: float
    status: str = "idle"  # idle, scraping, checking, traffic, scanning
    current_operation: str = ""

    # Operation stats
    requests: int = 0
    success: int = 0
    failed: int = 0
    proxies_found: int = 0
    proxies_checked: int = 0
    proxies_alive: int = 0

    # Resource stats
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_percent: float = 0.0


@dataclass
class AggregatedStats:
    """Aggregated statistics from all slaves."""

    active_slaves: int = 0
    total_requests: int = 0
    total_success: int = 0
    total_failed: int = 0
    total_proxies_found: int = 0
    total_proxies_checked: int = 0
    total_proxies_alive: int = 0
    avg_cpu: float = 0.0
    avg_memory: float = 0.0


@dataclass
class ScanResultEntry:
    """A single scan result entry."""

    slave_id: str
    slave_name: str
    ip: str
    port: int
    service: str  # "ssh" or "rdp"
    banner: str = ""
    fingerprint: str = ""
    version: str = ""
    scan_time: float = 0.0
    has_valid_credentials: bool = False
    username: str = ""
    timestamp: float = 0.0


class MasterServer:
    """
    Thread-safe wrapper around WebSocketServer for GUI integration.

    Features:
    - Runs WebSocket server in background thread
    - GUI-safe callbacks via callback_wrapper
    - Command distribution to slaves
    - Stats aggregation from all connected slaves

    Usage:
        master = MasterServer(
            host="0.0.0.0",
            port=8765,
            secret_key="your-secret-key-here",
            callback_wrapper=lambda cb: self.after(0, cb),
            on_log=lambda msg: self.log(msg),
        )
        master.start()
        # ... use master ...
        master.stop()
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        secret_key: str = "",
        heartbeat_interval: int = 30,
        timeout_seconds: int = 60,
        callback_wrapper: Callable[[Callable], None] | None = None,
        on_slave_connected: Callable[[str, dict], None] | None = None,
        on_slave_disconnected: Callable[[str], None] | None = None,
        on_message: Callable[[str, MessageType, dict], None] | None = None,
        on_scan_result: Callable[[ScanResultEntry], None] | None = None,
        on_log: Callable[[str], None] | None = None,
    ):
        """
        Initialize MasterServer.

        Args:
            host: Server bind address
            port: Server port
            secret_key: Shared secret for HMAC authentication (32+ chars)
            heartbeat_interval: Heartbeat interval in seconds
            timeout_seconds: Connection timeout after missed heartbeats
            callback_wrapper: Function to schedule callbacks on GUI thread
                              e.g., lambda cb: self.after(0, cb)
            on_slave_connected: Callback when slave connects (slave_id, info)
            on_slave_disconnected: Callback when slave disconnects (slave_id)
            on_message: Callback for incoming messages (slave_id, type, payload)
            on_scan_result: Callback for each new scan result found
            on_log: Callback for log messages
        """
        self.host = host
        self.port = port
        self.secret_key = secret_key
        self.heartbeat_interval = heartbeat_interval
        self.timeout_seconds = timeout_seconds

        # Callbacks
        self._callback_wrapper = callback_wrapper or (lambda cb: cb())
        self._on_slave_connected = on_slave_connected
        self._on_slave_disconnected = on_slave_disconnected
        self._on_message = on_message
        self._on_scan_result = on_scan_result
        self._on_log = on_log

        # Internal state
        self._server: WebSocketServer | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()

        # Data storage
        self._slave_stats: dict[str, SlaveStats] = {}
        self._scan_results: list[ScanResultEntry] = []

        self.logger = logging.getLogger(__name__)

    def _log(self, message: str) -> None:
        """Log message via callback (GUI-safe)."""
        self.logger.info(message)
        if self._on_log:
            self._callback_wrapper(lambda: self._on_log(message))

    def _wrap_callback(self, callback: Callable | None, *args) -> None:
        """Execute callback on GUI thread."""
        if callback:
            self._callback_wrapper(lambda: callback(*args))

    # ==================== Server Lifecycle ====================

    def start(self) -> bool:
        """
        Start the WebSocket server in a background thread.

        Returns:
            True if started successfully, False otherwise
        """
        with self._lock:
            if self._running:
                self._log("Server already running")
                return False

            if not self.secret_key or len(self.secret_key) < 32:
                self._log("Error: Secret key must be at least 32 characters")
                return False

            try:
                # Create new event loop for background thread
                self._loop = asyncio.new_event_loop()

                # Create WebSocket server
                self._server = WebSocketServer(
                    host=self.host,
                    port=self.port,
                    secret_key=self.secret_key,
                    heartbeat_interval=self.heartbeat_interval,
                    timeout_seconds=self.timeout_seconds,
                    on_message=self._handle_message,
                    on_slave_connected=self._handle_slave_connected,
                    on_slave_disconnected=self._handle_slave_disconnected,
                )

                # Start background thread
                self._thread = threading.Thread(
                    target=self._run_server_loop,
                    name="MasterServer",
                    daemon=True,
                )
                self._thread.start()

                # Wait for server to start (up to 5 seconds)
                start_time = time.time()
                while not self._running and time.time() - start_time < 5:
                    time.sleep(0.1)

                if self._running:
                    self._log(f"Master server started on {self.host}:{self.port}")
                    return True
                else:
                    self._log("Failed to start server within timeout")
                    return False

            except Exception as e:
                self._log(f"Error starting server: {e}")
                self.logger.error(f"Server start error: {e}", exc_info=True)
                return False

    def _run_server_loop(self) -> None:
        """Run the async event loop in background thread."""
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._server.start())
            self._running = True

            # Run until stopped
            self._loop.run_forever()

        except Exception as e:
            self.logger.error(f"Server loop error: {e}", exc_info=True)
        finally:
            self._running = False

            # Cleanup
            if self._server:
                with contextlib.suppress(Exception):
                    self._loop.run_until_complete(self._server.stop())

            self._loop.close()

    def stop(self) -> None:
        """Stop the WebSocket server."""
        with self._lock:
            if not self._running:
                return

            self._log("Stopping master server...")
            self._running = False

            # Schedule server stop on event loop
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)

            # Wait for thread to finish
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5)

            self._slave_stats.clear()
            self._scan_results.clear()
            self._log("Master server stopped")

    # ==================== Message Handlers ====================

    def _handle_message(
        self, slave_id: str, message_type: MessageType, payload: dict
    ) -> None:
        """Handle incoming message from slave."""
        try:
            # Update slave stats based on message type
            if message_type == MessageType.STATUS_UPDATE:
                self._update_slave_status(slave_id, payload)
            elif message_type == MessageType.SCRAPE_PROGRESS:
                self._update_scrape_progress(slave_id, payload)
            elif message_type == MessageType.CHECK_PROGRESS:
                self._update_check_progress(slave_id, payload)
            elif message_type == MessageType.TRAFFIC_STATS:
                self._update_traffic_stats(slave_id, payload)
            elif message_type == MessageType.SCAN_RESULTS:
                self._update_scan_results(slave_id, payload)
            elif message_type in (
                MessageType.LOG_INFO,
                MessageType.LOG_WARNING,
                MessageType.LOG_ERROR,
            ):
                self._handle_slave_log(slave_id, message_type, payload)

            # Forward to user callback
            if self._on_message:
                self._wrap_callback(
                    self._on_message, slave_id, message_type, payload
                )

        except Exception as e:
            self.logger.error(f"Error handling message: {e}", exc_info=True)

    def _handle_slave_connected(self, slave_id: str, info: dict) -> None:
        """Handle slave connection."""
        # Create stats entry
        self._slave_stats[slave_id] = SlaveStats(
            slave_id=slave_id,
            slave_name=info.get("name", "Unknown"),
            ip_address=info.get("ip", ""),
            connected_at=info.get("connected_at", time.time()),
            last_heartbeat=time.time(),
        )

        self._log(f"Slave connected: {info.get('name', slave_id)}")

        if self._on_slave_connected:
            self._wrap_callback(self._on_slave_connected, slave_id, info)

    def _handle_slave_disconnected(self, slave_id: str) -> None:
        """Handle slave disconnection."""
        stats = self._slave_stats.pop(slave_id, None)
        name = stats.slave_name if stats else slave_id

        self._log(f"Slave disconnected: {name}")

        if self._on_slave_disconnected:
            self._wrap_callback(self._on_slave_disconnected, slave_id)

    def _handle_slave_log(
        self, slave_id: str, log_type: MessageType, payload: dict
    ) -> None:
        """Handle log message from slave."""
        stats = self._slave_stats.get(slave_id)
        name = stats.slave_name if stats else slave_id
        message = payload.get("message", "")
        level = log_type.value.replace("log_", "").upper()

        self._log(f"[{name}] [{level}] {message}")

    def _update_slave_status(self, slave_id: str, payload: dict) -> None:
        """Update slave status from status update message."""
        stats = self._slave_stats.get(slave_id)
        if not stats:
            return

        stats.status = payload.get("status", "idle")
        stats.current_operation = payload.get("operation", "")
        stats.cpu_percent = payload.get("cpu_percent", 0.0)
        stats.memory_percent = payload.get("memory_percent", 0.0)
        stats.disk_percent = payload.get("disk_percent", 0.0)
        stats.last_heartbeat = time.time()

    def _update_scrape_progress(self, slave_id: str, payload: dict) -> None:
        """Update slave scrape progress."""
        stats = self._slave_stats.get(slave_id)
        if not stats:
            return

        stats.status = "scraping"
        stats.proxies_found = payload.get("proxies_found", 0)

    def _update_check_progress(self, slave_id: str, payload: dict) -> None:
        """Update slave check progress."""
        stats = self._slave_stats.get(slave_id)
        if not stats:
            return

        stats.status = "checking"
        stats.proxies_checked = payload.get("checked", 0)
        stats.proxies_alive = payload.get("alive", 0)

    def _update_traffic_stats(self, slave_id: str, payload: dict) -> None:
        """Update slave traffic stats."""
        stats = self._slave_stats.get(slave_id)
        if not stats:
            return

        stats.status = "traffic"
        stats.requests = payload.get("total_requests", 0)
        stats.success = payload.get("success", 0)
        stats.failed = payload.get("failed", 0)

    def _update_scan_results(self, slave_id: str, payload: dict) -> None:
        """Update slave scan results and invoke callback."""
        stats = self._slave_stats.get(slave_id)
        if not stats:
            return

        stats.status = "scanning"
        
        # Parse results list
        results = payload.get("results", [])
        slave_name = stats.slave_name
        current_time = time.time()

        for res in results:
            entry = ScanResultEntry(
                slave_id=slave_id,
                slave_name=slave_name,
                ip=res.get("ip", ""),
                port=res.get("port", 0),
                service=res.get("service", "unknown"),
                banner=res.get("banner", ""),
                fingerprint=res.get("fingerprint", ""),
                version=res.get("version", ""),
                scan_time=res.get("scan_time", 0.0),
                has_valid_credentials=res.get("has_valid_credentials", False),
                username=res.get("username", ""),
                timestamp=current_time
            )
            
            self._scan_results.append(entry)
            
            # Notify via callback if registered
            if self._on_scan_result:
                self._wrap_callback(self._on_scan_result, entry)

    # ==================== Command Distribution ====================

    def send_command(
        self, slave_id: str, command_type: MessageType, params: dict
    ) -> bool:
        """
        Send command to specific slave.

        Args:
            slave_id: Target slave ID
            command_type: Command type (MessageType enum)
            params: Command parameters

        Returns:
            True if command was queued successfully
        """
        if not self._running or not self._loop:
            return False

        try:
            future = asyncio.run_coroutine_threadsafe(
                self._server.send_command(slave_id, command_type, params),
                self._loop,
            )
            return future.result(timeout=5)
        except Exception as e:
            self.logger.error(f"Error sending command: {e}")
            return False

    def broadcast_command(self, command_type: MessageType, params: dict) -> int:
        """
        Broadcast command to all connected slaves.

        Args:
            command_type: Command type (MessageType enum)
            params: Command parameters

        Returns:
            Number of slaves that received the command
        """
        if not self._running or not self._loop:
            return 0

        try:
            future = asyncio.run_coroutine_threadsafe(
                self._server.broadcast_command(command_type, params),
                self._loop,
            )
            return future.result(timeout=10)
        except Exception as e:
            self.logger.error(f"Error broadcasting command: {e}")
            return 0

    # ==================== Task Distribution ====================

    def start_scrape_on_slaves(
        self,
        slave_ids: list[str] | None = None,
        sources: list[str] | None = None,
    ) -> int:
        """
        Start proxy scraping on specified slaves.

        Args:
            slave_ids: List of slave IDs (None = all slaves)
            sources: List of source URLs (None = use default sources)

        Returns:
            Number of slaves that received the command
        """
        params = {}
        if sources:
            params["sources"] = sources

        if slave_ids:
            count = 0
            for slave_id in slave_ids:
                if self.send_command(slave_id, MessageType.START_SCRAPE, params):
                    count += 1
            self._log(f"Started scrape on {count} slaves")
            return count
        else:
            count = self.broadcast_command(MessageType.START_SCRAPE, params)
            self._log(f"Broadcast scrape to {count} slaves")
            return count

    def start_check_on_slaves(
        self,
        slave_ids: list[str] | None = None,
        proxies: list[str] | None = None,
        threads: int = 100,
        timeout: int = 5000,
    ) -> int:
        """
        Start proxy checking on specified slaves.

        Args:
            slave_ids: List of slave IDs (None = all slaves)
            proxies: List of proxy strings (None = use scraped proxies)
            threads: Number of concurrent threads
            timeout: Check timeout in milliseconds

        Returns:
            Number of slaves that received the command
        """
        params = {
            "threads": threads,
            "timeout": timeout,
        }
        if proxies:
            params["proxies"] = proxies

        if slave_ids:
            count = 0
            for slave_id in slave_ids:
                if self.send_command(slave_id, MessageType.START_CHECK, params):
                    count += 1
            self._log(f"Started check on {count} slaves")
            return count
        else:
            count = self.broadcast_command(MessageType.START_CHECK, params)
            self._log(f"Broadcast check to {count} slaves")
            return count

    def start_traffic_on_slaves(
        self,
        target_url: str,
        slave_ids: list[str] | None = None,
        threads: int = 50,
        duration: int = 0,
        min_view_time: int = 5,
        max_view_time: int = 30,
    ) -> int:
        """
        Start traffic generation on specified slaves.

        Args:
            target_url: Target URL for traffic
            slave_ids: List of slave IDs (None = all slaves)
            threads: Number of concurrent threads per slave
            duration: Duration in seconds (0 = infinite)
            min_view_time: Minimum view time per request
            max_view_time: Maximum view time per request

        Returns:
            Number of slaves that received the command
        """
        params = {
            "target_url": target_url,
            "threads": threads,
            "duration": duration,
            "min_view_time": min_view_time,
            "max_view_time": max_view_time,
        }

        if slave_ids:
            count = 0
            for slave_id in slave_ids:
                if self.send_command(slave_id, MessageType.START_TRAFFIC, params):
                    count += 1
            self._log(f"Started traffic on {count} slaves")
            return count
        else:
            count = self.broadcast_command(MessageType.START_TRAFFIC, params)
            self._log(f"Broadcast traffic to {count} slaves")
            return count

    def stop_slaves(self, slave_ids: list[str] | None = None) -> int:
        """
        Stop current operation on specified slaves.

        Args:
            slave_ids: List of slave IDs (None = all slaves)

        Returns:
            Number of slaves that received the command
        """
        if slave_ids:
            count = 0
            for slave_id in slave_ids:
                if self.send_command(slave_id, MessageType.STOP, {}):
                    count += 1
            self._log(f"Stopped {count} slaves")
            return count
        else:
            count = self.broadcast_command(MessageType.STOP, {})
            self._log(f"Broadcast stop to {count} slaves")
            return count

    def start_scan_on_slaves(
        self,
        targets: list[str],
        slave_ids: list[str] | None = None,
        ports: list[int] | None = None,
        timeout: float = 3.0,
        max_concurrent: int = 100,
        grab_banner: bool = True,
        fingerprint: bool = True,
        test_credentials: bool = False,
        usernames: list[str] | None = None,
        passwords: list[str] | None = None,
    ) -> int:
        """
        Start network scanning on specified slaves.

        Args:
            targets: List of target IPs, CIDRs, or ranges
            slave_ids: List of slave IDs (None = all slaves)
            ports: Ports to scan (default: [22, 3389])
            timeout: Connection timeout in seconds
            max_concurrent: Max concurrent connections per slave
            grab_banner: Whether to grab service banners
            fingerprint: Whether to fingerprint services
            test_credentials: Whether to test SSH credentials
            usernames: SSH usernames to test
            passwords: SSH passwords to test

        Returns:
            Number of slaves that received the command
        """
        params = {
            "targets": targets,
            "ports": ports or [22, 3389],
            "timeout": timeout,
            "max_concurrent": max_concurrent,
            "grab_banner": grab_banner,
            "fingerprint": fingerprint,
            "test_credentials": test_credentials,
            "usernames": usernames or [],
            "passwords": passwords or [],
        }

        if slave_ids:
            count = 0
            for slave_id in slave_ids:
                if self.send_command(slave_id, MessageType.START_SCAN, params):
                    count += 1
            self._log(f"Started scan on {count} slaves")
            return count
        else:
            count = self.broadcast_command(MessageType.START_SCAN, params)
            self._log(f"Broadcast scan to {count} slaves")
            return count

    def request_status(self, slave_ids: list[str] | None = None) -> int:
        """
        Request status update from specified slaves.

        Args:
            slave_ids: List of slave IDs (None = all slaves)

        Returns:
            Number of slaves that received the command
        """
        if slave_ids:
            count = 0
            for slave_id in slave_ids:
                if self.send_command(slave_id, MessageType.GET_STATUS, {}):
                    count += 1
            return count
        else:
            return self.broadcast_command(MessageType.GET_STATUS, {})

    # ==================== Slave Management ====================

    def get_slaves(self) -> list[SlaveStats]:
        """
        Get list of connected slaves with their stats.

        Returns:
            List of SlaveStats objects
        """
        return list(self._slave_stats.values())

    def get_slave(self, slave_id: str) -> SlaveStats | None:
        """
        Get stats for specific slave.

        Args:
            slave_id: Slave ID

        Returns:
            SlaveStats or None if not found
        """
        return self._slave_stats.get(slave_id)

    def disconnect_slave(self, slave_id: str) -> bool:
        """
        Disconnect a specific slave.

        Args:
            slave_id: Slave ID to disconnect

        Returns:
            True if disconnect was initiated
        """
        if not self._running or not self._loop or not self._server:
            return False

        try:
            # Access server's internal disconnect method
            future = asyncio.run_coroutine_threadsafe(
                self._server._disconnect_slave(slave_id, reason="Master requested"),
                self._loop,
            )
            future.result(timeout=5)
            return True
        except Exception as e:
            self.logger.error(f"Error disconnecting slave: {e}")
            return False

    def get_aggregated_stats(self) -> AggregatedStats:
        """
        Get aggregated statistics from all slaves.

        Returns:
            AggregatedStats object with totals
        """
        stats = AggregatedStats()
        slaves = list(self._slave_stats.values())

        if not slaves:
            return stats

        stats.active_slaves = len(slaves)

        for slave in slaves:
            stats.total_requests += slave.requests
            stats.total_success += slave.success
            stats.total_failed += slave.failed
            stats.total_proxies_found += slave.proxies_found
            stats.total_proxies_checked += slave.proxies_checked
            stats.total_proxies_alive += slave.proxies_alive
            stats.avg_cpu += slave.cpu_percent
            stats.avg_memory += slave.memory_percent

        if stats.active_slaves > 0:
            stats.avg_cpu /= stats.active_slaves
            stats.avg_memory /= stats.active_slaves

        return stats

    def get_scan_results(self) -> list[ScanResultEntry]:
        """
        Get all collected scan results.

        Returns:
            List of ScanResultEntry objects
        """
        return list(self._scan_results)

    def clear_scan_results(self) -> None:
        """Clear all collected scan results."""
        self._scan_results.clear()

    # ==================== Properties ====================

    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running

    @property
    def slave_count(self) -> int:
        """Get number of connected slaves."""
        return len(self._slave_stats)

    @property
    def server_address(self) -> str:
        """Get server address string."""
        return f"{self.host}:{self.port}"