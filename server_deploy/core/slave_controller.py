"""
Slave Controller - Command dispatcher and operation lifecycle manager.

Handles commands from master, manages operations (scraping, checking, traffic),
reports stats and logs, and monitors system resources.
"""

import asyncio
import contextlib
import logging
import platform
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .models import ProxyConfig, TrafficConfig, TrafficStats
from .websocket_client import WebSocketClient
from .websocket_server import MessageType


class OperationType(Enum):
    """Types of operations the slave can perform."""

    NONE = "none"
    SCRAPE = "scrape"
    CHECK = "check"
    TRAFFIC = "traffic"
    SCAN = "scan"


@dataclass
class OperationStatus:
    """Status of the current operation."""

    type: OperationType = OperationType.NONE
    running: bool = False
    started_at: float = 0.0
    progress: int = 0
    total: int = 0
    message: str = ""


@dataclass
class ResourceStats:
    """System resource statistics."""

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    disk_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0


@dataclass
class SlaveStatus:
    """Complete slave status for reporting to master."""

    slave_name: str = ""
    connected: bool = False
    operation: OperationStatus = field(default_factory=OperationStatus)
    resources: ResourceStats = field(default_factory=ResourceStats)
    uptime_seconds: float = 0.0
    platform: str = ""
    python_version: str = ""
    last_updated: float = field(default_factory=time.time)


class SlaveController:
    """
    Controller for slave node operations.

    Manages WebSocket connection, command dispatching, operation lifecycle,
    stats reporting, log forwarding, and resource monitoring.
    """

    def __init__(
        self,
        master_host: str,
        master_port: int,
        secret_key: str,
        slave_name: str,
        settings: dict | None = None,
        connection_mode: str = "direct",
    ):
        """
        Initialize slave controller.

        Args:
            master_host: Master/Relay server hostname/IP (or Cloudflare URL)
            master_port: Master/Relay server port
            secret_key: Shared secret for authentication
            slave_name: Name of this slave node
            settings: Additional settings dict
            connection_mode: "direct", "relay", or "cloudflare"
        """
        self.master_host = master_host
        self.master_port = master_port
        self.secret_key = secret_key
        self.slave_name = slave_name
        self.settings = settings or {}
        self.connection_mode = connection_mode

        # WebSocket client
        self.client: WebSocketClient | None = None

        # State
        self._running = False
        self._start_time = time.time()
        self._status = SlaveStatus(
            slave_name=slave_name,
            platform=platform.system(),
            python_version=platform.python_version(),
        )

        # Current operation state
        self._operation_task: asyncio.Task | None = None
        self._operation_stop_event = asyncio.Event()

        # Stats reporting interval
        self._stats_interval = settings.get("stats_interval", 5.0)
        self._stats_task: asyncio.Task | None = None

        # Resource monitoring
        self._resource_monitor_task: asyncio.Task | None = None
        self._resource_interval = settings.get("resource_interval", 30.0)

        # Proxies cache (received from master or scraped)
        self._proxies: list[ProxyConfig] = []

        # Command handlers
        self._handlers: dict[MessageType, Callable] = {
            MessageType.START_SCRAPE: self._handle_start_scrape,
            MessageType.START_CHECK: self._handle_start_check,
            MessageType.START_TRAFFIC: self._handle_start_traffic,
            MessageType.START_SCAN: self._handle_start_scan,
            MessageType.STOP: self._handle_stop,
            MessageType.GET_STATUS: self._handle_get_status,
            MessageType.UPDATE_CONFIG: self._handle_update_config,
        }

        self.logger = logging.getLogger(__name__)

    async def run(self):
        """Main controller loop."""
        self._running = True
        self._start_time = time.time()

        # Create WebSocket client
        self.client = WebSocketClient(
            master_host=self.master_host,
            master_port=self.master_port,
            secret_key=self.secret_key,
            slave_name=self.slave_name,
            on_command=self._on_command,
            on_connected=self._on_connected,
            on_disconnected=self._on_disconnected,
            connection_mode=self.connection_mode,
            client_id=self.slave_name,
        )

        self.logger.info(f"Starting slave controller: {self.slave_name} ({self.connection_mode} mode)")

        # Start resource monitoring
        self._resource_monitor_task = asyncio.create_task(self._resource_monitor_loop())

        try:
            # Run WebSocket client (handles auto-reconnect)
            await self.client.run()
        except asyncio.CancelledError:
            self.logger.info("Controller cancelled")
        except Exception as e:
            self.logger.error(f"Controller error: {e}", exc_info=True)
        finally:
            self._running = False

    async def stop(self):
        """Stop the controller gracefully."""
        self.logger.info("Stopping controller...")
        self._running = False

        # Stop current operation
        await self._stop_operation()

        # Stop WebSocket client
        if self.client:
            self.client.stop()

        # Cancel monitoring tasks
        for task in [self._stats_task, self._resource_monitor_task]:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    async def cleanup(self):
        """Cleanup resources."""
        self.logger.info("Cleaning up controller resources...")

        # Ensure everything is stopped
        await self.stop()

    def _on_connected(self):
        """Callback when connected to master."""
        self.logger.info("Connected to master server")
        self._status.connected = True

        # Start stats reporting
        if self._stats_task:
            self._stats_task.cancel()
        self._stats_task = asyncio.create_task(self._stats_report_loop())

    def _on_disconnected(self):
        """Callback when disconnected from master."""
        self.logger.warning("Disconnected from master server")
        self._status.connected = False

        # Stop stats reporting
        if self._stats_task:
            self._stats_task.cancel()
            self._stats_task = None

    def _on_command(self, message_type: MessageType, payload: dict):
        """
        Callback for commands from master.

        Dispatches to appropriate handler based on message type.
        """
        handler = self._handlers.get(message_type)

        if handler:
            self.logger.info(f"Received command: {message_type.value}")
            # Run handler in event loop (handlers are sync but may need async ops)
            asyncio.create_task(self._run_handler(handler, payload))
        else:
            self.logger.warning(f"Unknown command: {message_type.value}")

    async def _run_handler(self, handler: Callable, payload: dict):
        """Run command handler (handles both sync and async handlers)."""
        try:
            result = handler(payload)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            self.logger.error(f"Handler error: {e}", exc_info=True)
            await self._send_log("error", f"Handler error: {e}")

    # -------------------------------------------------------------------------
    # Command Handlers
    # -------------------------------------------------------------------------

    async def _handle_start_scrape(self, payload: dict):
        """Handle START_SCRAPE command."""
        if self._is_operation_running():
            await self._send_log("warning", "Cannot start scrape: operation already running")
            return

        sources = payload.get("sources", [])
        protocols = payload.get("protocols", ["http", "socks4", "socks5"])
        max_threads = payload.get("max_threads", 20)

        if not sources:
            await self._send_log("error", "No sources provided for scraping")
            return

        self.logger.info(f"Starting proxy scrape: {len(sources)} sources, {max_threads} threads")
        await self._send_log("info", f"Starting proxy scrape: {len(sources)} sources")

        # Update status
        self._status.operation = OperationStatus(
            type=OperationType.SCRAPE,
            running=True,
            started_at=time.time(),
            total=len(sources),
        )

        # Start operation in background
        self._operation_stop_event.clear()
        self._operation_task = asyncio.create_task(
            self._run_scrape_operation(sources, protocols, max_threads)
        )

    async def _run_scrape_operation(
        self, sources: list[str], protocols: list[str], max_threads: int
    ):
        """Execute proxy scraping operation."""
        try:
            from .proxy_manager import ThreadedProxyManager

            manager = ThreadedProxyManager()
            scraped_count = [0]

            def on_progress(bytes_count: int):
                scraped_count[0] += 1
                self._status.operation.progress = scraped_count[0]

            # Run scrape in executor (it's blocking/threaded)
            loop = asyncio.get_running_loop()
            proxies = await loop.run_in_executor(
                None,
                lambda: manager.scrape(
                    sources=sources,
                    protocols=protocols,
                    max_threads=max_threads,
                    on_progress=on_progress,
                ),
            )

            # Store proxies
            self._proxies = proxies

            # Report completion
            if self.client and self.client.is_connected:
                await self.client.send_stats(
                    MessageType.SCRAPE_PROGRESS,
                    {
                        "status": "complete",
                        "total_proxies": len(proxies),
                        "sources_processed": scraped_count[0],
                    },
                )

            await self._send_log("info", f"Scrape complete: {len(proxies)} proxies found")

        except asyncio.CancelledError:
            await self._send_log("info", "Scrape operation cancelled")
        except Exception as e:
            self.logger.error(f"Scrape error: {e}", exc_info=True)
            await self._send_log("error", f"Scrape failed: {e}")
        finally:
            self._status.operation.running = False
            self._operation_task = None

    async def _handle_start_check(self, payload: dict):
        """Handle START_CHECK command."""
        if self._is_operation_running():
            await self._send_log("warning", "Cannot start check: operation already running")
            return

        # Use stored proxies or proxies from payload
        proxies = payload.get("proxies", [])
        if proxies:
            # Convert dict proxies to ProxyConfig
            self._proxies = [
                ProxyConfig(
                    host=p.get("host", ""),
                    port=p.get("port", 0),
                    protocol=p.get("protocol", "http"),
                )
                for p in proxies
            ]
        elif not self._proxies:
            await self._send_log("error", "No proxies to check")
            return

        max_threads = payload.get("max_threads", 100)
        timeout = payload.get("timeout", 5000)

        self.logger.info(f"Starting proxy check: {len(self._proxies)} proxies, {max_threads} threads")
        await self._send_log("info", f"Starting proxy check: {len(self._proxies)} proxies")

        self._status.operation = OperationStatus(
            type=OperationType.CHECK,
            running=True,
            started_at=time.time(),
            total=len(self._proxies),
        )

        self._operation_stop_event.clear()
        self._operation_task = asyncio.create_task(
            self._run_check_operation(max_threads, timeout)
        )

    async def _run_check_operation(self, max_threads: int, timeout: int):
        """Execute proxy checking operation."""
        try:
            from .proxy_manager import ThreadedProxyManager

            manager = ThreadedProxyManager()
            checked_count = [0]
            active_count = [0]

            def on_result(result):
                checked_count[0] += 1
                if result.status == "Active":
                    active_count[0] += 1
                self._status.operation.progress = checked_count[0]

                # Report progress periodically
                if checked_count[0] % 50 == 0 and self.client and self.client.is_connected:
                    asyncio.create_task(
                        self.client.send_stats(
                            MessageType.CHECK_PROGRESS,
                            {
                                "checked": checked_count[0],
                                "active": active_count[0],
                                "total": len(self._proxies),
                            },
                        )
                    )

            # Run check in executor
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(
                None,
                lambda: manager.check_proxies(
                    proxies=self._proxies,
                    max_threads=max_threads,
                    timeout_ms=timeout,
                    on_result=on_result,
                ),
            )

            # Filter active proxies
            active_proxies = [r.proxy for r in results if r.status == "Active"]
            self._proxies = active_proxies

            # Report completion
            if self.client and self.client.is_connected:
                await self.client.send_stats(
                    MessageType.CHECK_PROGRESS,
                    {
                        "status": "complete",
                        "checked": checked_count[0],
                        "active": len(active_proxies),
                        "total": len(results),
                    },
                )

            await self._send_log(
                "info", f"Check complete: {len(active_proxies)}/{len(results)} proxies active"
            )

        except asyncio.CancelledError:
            await self._send_log("info", "Check operation cancelled")
        except Exception as e:
            self.logger.error(f"Check error: {e}", exc_info=True)
            await self._send_log("error", f"Check failed: {e}")
        finally:
            self._status.operation.running = False
            self._operation_task = None

    async def _handle_start_traffic(self, payload: dict):
        """Handle START_TRAFFIC command."""
        if self._is_operation_running():
            await self._send_log("warning", "Cannot start traffic: operation already running")
            return

        # Get traffic config from payload
        config_dict = payload.get("config", {})
        if not config_dict.get("target_url"):
            await self._send_log("error", "No target URL provided")
            return

        # Use proxies from payload or stored proxies
        proxies = payload.get("proxies", [])
        if proxies:
            self._proxies = [
                ProxyConfig(
                    host=p.get("host", ""),
                    port=p.get("port", 0),
                    protocol=p.get("protocol", "http"),
                )
                for p in proxies
            ]

        if not self._proxies:
            await self._send_log("warning", "No proxies available, traffic will run without proxies")

        # Build TrafficConfig
        config = TrafficConfig(
            target_url=config_dict.get("target_url", ""),
            max_threads=config_dict.get("max_threads", 10),
            total_visits=config_dict.get("total_visits", 0),
            min_duration=config_dict.get("min_duration", 1),
            max_duration=config_dict.get("max_duration", 5),
            headless=config_dict.get("headless", True),
            verify_ssl=config_dict.get("verify_ssl", True),
            burst_mode=config_dict.get("burst_mode", False),
            burst_requests=config_dict.get("burst_requests", 10),
            burst_sleep_min=config_dict.get("burst_sleep_min", 2.0),
            burst_sleep_max=config_dict.get("burst_sleep_max", 5.0),
        )

        self.logger.info(
            f"Starting traffic to {config.target_url}: "
            f"{config.max_threads} threads, {len(self._proxies)} proxies"
        )
        await self._send_log(
            "info", f"Starting traffic: {config.target_url}, {config.max_threads} threads"
        )

        self._status.operation = OperationStatus(
            type=OperationType.TRAFFIC,
            running=True,
            started_at=time.time(),
            total=config.total_visits,
        )

        self._operation_stop_event.clear()
        self._operation_task = asyncio.create_task(self._run_traffic_operation(config))

    async def _run_traffic_operation(self, config: TrafficConfig):
        """Execute traffic generation operation."""
        try:
            from .engine import AsyncTrafficEngine

            # Stats tracking
            last_stats: TrafficStats | None = None

            def on_update(stats: TrafficStats):
                nonlocal last_stats
                last_stats = stats
                self._status.operation.progress = stats.total_requests

            def on_log(message: str):
                # Forward logs to master (rate limited)
                if "Error" in message or "Failed" in message:
                    asyncio.create_task(self._send_log("warning", message))

            # Create engine
            engine = AsyncTrafficEngine(
                config=config,
                proxies=self._proxies,
                on_update=on_update,
                on_log=on_log,
            )

            # Run engine in background and report stats periodically
            engine_task = asyncio.create_task(engine.run())

            while not engine_task.done() and not self._operation_stop_event.is_set():
                # Report stats to master
                if last_stats and self.client and self.client.is_connected:
                    await self.client.send_stats(
                        MessageType.TRAFFIC_STATS,
                        {
                            "success": last_stats.success,
                            "failed": last_stats.failed,
                            "total_requests": last_stats.total_requests,
                            "active_threads": last_stats.active_threads,
                            "active_proxies": last_stats.active_proxies,
                        },
                    )
                await asyncio.sleep(self._stats_interval)

            # If stop was requested, stop engine
            if self._operation_stop_event.is_set():
                engine.running = False

            # Wait for engine to finish
            try:
                await asyncio.wait_for(engine_task, timeout=10.0)
            except asyncio.TimeoutError:
                engine_task.cancel()

            # Final stats report
            if last_stats and self.client and self.client.is_connected:
                await self.client.send_stats(
                    MessageType.TRAFFIC_STATS,
                    {
                        "status": "complete",
                        "success": last_stats.success,
                        "failed": last_stats.failed,
                        "total_requests": last_stats.total_requests,
                    },
                )

            await self._send_log(
                "info",
                f"Traffic complete: {last_stats.success if last_stats else 0} success, "
                f"{last_stats.failed if last_stats else 0} failed",
            )

        except asyncio.CancelledError:
            await self._send_log("info", "Traffic operation cancelled")
        except Exception as e:
            self.logger.error(f"Traffic error: {e}", exc_info=True)
            await self._send_log("error", f"Traffic failed: {e}")
        finally:
            self._status.operation.running = False
            self._operation_task = None

    async def _handle_start_scan(self, payload: dict):
        """Handle START_SCAN command - SSH/RDP network scanning."""
        if self._is_operation_running():
            await self._send_log("warning", "Cannot start scan: operation already running")
            return

        # Get scan configuration from payload
        targets = payload.get("targets", [])
        ports = payload.get("ports", [22, 3389])
        timeout = payload.get("timeout", 3.0)
        max_concurrent = payload.get("max_concurrent", 100)
        grab_banner = payload.get("grab_banner", True)
        fingerprint = payload.get("fingerprint", True)

        # Credential testing (requires explicit opt-in)
        test_credentials = payload.get("test_credentials", False)
        usernames = payload.get("usernames", [])
        passwords = payload.get("passwords", [])

        if not targets:
            await self._send_log("error", "No targets provided for scanning")
            return

        self.logger.info(
            f"Starting network scan: {len(targets)} targets, "
            f"ports {ports}, {max_concurrent} concurrent"
        )
        await self._send_log(
            "info", f"Starting network scan: {len(targets)} targets, ports {ports}"
        )

        self._status.operation = OperationStatus(
            type=OperationType.SCAN,
            running=True,
            started_at=time.time(),
            total=len(targets) * len(ports),
        )

        self._operation_stop_event.clear()
        self._operation_task = asyncio.create_task(
            self._run_scan_operation(
                targets=targets,
                ports=ports,
                timeout=timeout,
                max_concurrent=max_concurrent,
                grab_banner=grab_banner,
                fingerprint=fingerprint,
                test_credentials=test_credentials,
                usernames=usernames,
                passwords=passwords,
            )
        )

    async def _run_scan_operation(
        self,
        targets: list[str],
        ports: list[int],
        timeout: float,
        max_concurrent: int,
        grab_banner: bool,
        fingerprint: bool,
        test_credentials: bool,
        usernames: list[str],
        passwords: list[str],
    ):
        """Execute network scanning operation."""
        try:
            from .scanner import NetworkScanner, ScanConfig, ScanResult, ScanStatus

            # Track results
            scan_results: list[dict] = []
            stats = {"scanned": 0, "open": 0, "ssh": 0, "rdp": 0, "credentials_valid": 0}

            def on_result(result: ScanResult):
                """Callback for each scan result."""
                stats["scanned"] += 1
                self._status.operation.progress = stats["scanned"]

                if result.status == ScanStatus.OPEN:
                    stats["open"] += 1
                    if result.service.value == "ssh":
                        stats["ssh"] += 1
                    elif result.service.value == "rdp":
                        stats["rdp"] += 1

                    # Store open port results
                    result_dict = {
                        "ip": result.ip,
                        "port": result.port,
                        "service": result.service.value,
                        "banner": result.banner,
                        "fingerprint": result.fingerprint,
                        "version": result.version,
                        "scan_time": result.scan_time,
                    }

                    # Include credential info if tested
                    if result.credential_status.value == "valid":
                        stats["credentials_valid"] += 1
                        result_dict["credential_status"] = "valid"
                        result_dict["username"] = result.valid_username
                        # Note: Password not sent for security
                        result_dict["has_valid_credentials"] = True

                    scan_results.append(result_dict)

                # Report progress periodically
                if stats["scanned"] % 100 == 0 and self.client and self.client.is_connected:
                    asyncio.create_task(
                        self.client.send_stats(
                            MessageType.SCAN_RESULTS,
                            {
                                "status": "in_progress",
                                **stats,
                            },
                        )
                    )

            def on_progress(scan_stats):
                """Progress callback from scanner."""
                pass  # Handled in on_result

            def on_log(message: str):
                """Log callback from scanner."""
                if "Error" in message or "error" in message:
                    asyncio.create_task(self._send_log("warning", message))

            # Create scanner and config
            scanner = NetworkScanner(
                on_result=on_result,
                on_progress=on_progress,
                on_log=on_log,
            )

            config = ScanConfig(
                targets=targets,
                ports=ports,
                timeout=timeout,
                max_concurrent=max_concurrent,
                grab_banner=grab_banner,
                fingerprint=fingerprint,
                test_credentials=test_credentials,
                usernames=usernames,
                passwords=passwords,
            )

            # Run scan (async)
            await scanner.scan(config)

            # Check if stop was requested
            if self._operation_stop_event.is_set():
                scanner.stop()

            # Report final results
            if self.client and self.client.is_connected:
                await self.client.send_stats(
                    MessageType.SCAN_RESULTS,
                    {
                        "status": "complete",
                        "scanned": stats["scanned"],
                        "open": stats["open"],
                        "ssh": stats["ssh"],
                        "rdp": stats["rdp"],
                        "credentials_valid": stats["credentials_valid"],
                        "results": scan_results,
                    },
                )

            await self._send_log(
                "info",
                f"Scan complete: {stats['open']} open ports "
                f"({stats['ssh']} SSH, {stats['rdp']} RDP)",
            )

        except asyncio.CancelledError:
            await self._send_log("info", "Scan operation cancelled")
        except ImportError as e:
            self.logger.error(f"Scanner import error: {e}")
            await self._send_log("error", f"Scanner module not available: {e}")
        except Exception as e:
            self.logger.error(f"Scan error: {e}", exc_info=True)
            await self._send_log("error", f"Scan failed: {e}")
        finally:
            self._status.operation.running = False
            self._operation_task = None

    async def _handle_stop(self, payload: dict):
        """Handle STOP command."""
        self.logger.info("Received STOP command")
        await self._stop_operation()

    async def _stop_operation(self):
        """Stop the current operation."""
        if not self._is_operation_running():
            return

        self.logger.info("Stopping current operation...")
        self._operation_stop_event.set()

        if self._operation_task:
            try:
                await asyncio.wait_for(self._operation_task, timeout=10.0)
            except asyncio.TimeoutError:
                self.logger.warning("Operation stop timed out, cancelling...")
                self._operation_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._operation_task

        self._status.operation.running = False
        await self._send_log("info", "Operation stopped")

    async def _handle_get_status(self, payload: dict):
        """Handle GET_STATUS command."""
        # Update resource stats
        self._status.resources = self._get_resource_stats()
        self._status.uptime_seconds = time.time() - self._start_time
        self._status.last_updated = time.time()

        # Send status update
        if self.client and self.client.is_connected:
            await self.client.send_stats(
                MessageType.STATUS_UPDATE,
                {
                    "slave_name": self._status.slave_name,
                    "connected": self._status.connected,
                    "operation": {
                        "type": self._status.operation.type.value,
                        "running": self._status.operation.running,
                        "progress": self._status.operation.progress,
                        "total": self._status.operation.total,
                    },
                    "resources": {
                        "cpu_percent": self._status.resources.cpu_percent,
                        "memory_percent": self._status.resources.memory_percent,
                        "memory_used_mb": self._status.resources.memory_used_mb,
                        "disk_percent": self._status.resources.disk_percent,
                    },
                    "uptime_seconds": self._status.uptime_seconds,
                    "platform": self._status.platform,
                    "python_version": self._status.python_version,
                    "proxies_count": len(self._proxies),
                },
            )

    async def _handle_update_config(self, payload: dict):
        """Handle UPDATE_CONFIG command."""
        new_config = payload.get("config", {})

        if not new_config:
            await self._send_log("warning", "Empty config update received")
            return

        # Update local settings
        for key, value in new_config.items():
            self.settings[key] = value

        # Update intervals if changed
        if "stats_interval" in new_config:
            self._stats_interval = new_config["stats_interval"]
        if "resource_interval" in new_config:
            self._resource_interval = new_config["resource_interval"]

        # Persist config if path available
        config_path = self.settings.get("runtime_config_path")
        if config_path:
            try:
                import json
                Path(config_path).write_text(
                    json.dumps({"config": self.settings}, indent=2)
                )
            except Exception as e:
                self.logger.error(f"Failed to save config: {e}")

        await self._send_log("info", f"Config updated: {list(new_config.keys())}")

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _is_operation_running(self) -> bool:
        """Check if an operation is currently running."""
        return self._status.operation.running and self._operation_task is not None

    async def _send_log(self, level: str, message: str):
        """Send log message to master."""
        self.logger.log(
            getattr(logging, level.upper(), logging.INFO), f"[→Master] {message}"
        )
        if self.client and self.client.is_connected:
            await self.client.send_log(level, message)

    def _get_resource_stats(self) -> ResourceStats:
        """Get current system resource statistics."""
        stats = ResourceStats()

        try:
            import psutil

            # CPU
            stats.cpu_percent = psutil.cpu_percent(interval=0.1)

            # Memory
            mem = psutil.virtual_memory()
            stats.memory_percent = mem.percent
            stats.memory_used_mb = mem.used / (1024 * 1024)
            stats.memory_total_mb = mem.total / (1024 * 1024)

            # Disk (root partition or working directory)
            disk = psutil.disk_usage("/")
            stats.disk_percent = disk.percent
            stats.disk_used_gb = disk.used / (1024 * 1024 * 1024)
            stats.disk_total_gb = disk.total / (1024 * 1024 * 1024)

        except ImportError:
            # psutil not installed - return zeros
            pass
        except Exception as e:
            self.logger.debug(f"Error getting resource stats: {e}")

        return stats

    async def _stats_report_loop(self):
        """Periodically report status to master."""
        self.logger.debug("Stats report loop started")

        try:
            while self._running and self._status.connected:
                await asyncio.sleep(self._stats_interval)

                if not self._status.connected:
                    break

                # Send status update
                await self._handle_get_status({})

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Stats report loop error: {e}")

        self.logger.debug("Stats report loop stopped")

    async def _resource_monitor_loop(self):
        """Monitor system resources and log warnings."""
        self.logger.debug("Resource monitor loop started")

        try:
            while self._running:
                await asyncio.sleep(self._resource_interval)

                stats = self._get_resource_stats()
                self._status.resources = stats

                # Log warnings for high resource usage
                if stats.cpu_percent > 90:
                    self.logger.warning(f"High CPU usage: {stats.cpu_percent:.1f}%")
                if stats.memory_percent > 90:
                    self.logger.warning(f"High memory usage: {stats.memory_percent:.1f}%")
                if stats.disk_percent > 95:
                    self.logger.warning(f"Low disk space: {stats.disk_percent:.1f}% used")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Resource monitor loop error: {e}")

        self.logger.debug("Resource monitor loop stopped")
