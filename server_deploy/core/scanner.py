"""
Network Scanner Module for SSH/RDP Detection.

Provides async network scanning capabilities for discovering SSH and RDP services
on target IP ranges. Supports port scanning, banner grabbing, fingerprinting,
and optional credential testing (with explicit authorization).

IMPORTANT: This module is for AUTHORIZED SECURITY TESTING ONLY.
Only use on networks and systems you own or have explicit permission to test.
"""

import asyncio
import ipaddress
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

# Optional imports - graceful degradation if not available
try:
    import asyncssh

    ASYNCSSH_AVAILABLE = True
except ImportError:
    ASYNCSSH_AVAILABLE = False
    asyncssh = None


class ServiceType(Enum):
    """Discovered service types."""

    SSH = "ssh"
    RDP = "rdp"
    UNKNOWN = "unknown"


class ScanStatus(Enum):
    """Scan result status."""

    OPEN = "open"
    CLOSED = "closed"
    FILTERED = "filtered"
    ERROR = "error"


class CredentialStatus(Enum):
    """Credential test result."""

    VALID = "valid"
    INVALID = "invalid"
    NOT_TESTED = "not_tested"
    ERROR = "error"


@dataclass
class ScanResult:
    """Result of a single host/port scan."""

    ip: str
    port: int
    status: ScanStatus
    service: ServiceType = ServiceType.UNKNOWN
    banner: str = ""
    fingerprint: str = ""
    version: str = ""
    scan_time: float = 0.0
    error: str = ""

    # Credential testing (if enabled)
    credential_status: CredentialStatus = CredentialStatus.NOT_TESTED
    valid_username: str = ""
    valid_password: str = ""


@dataclass
class ScanConfig:
    """Configuration for a scan operation."""

    # Target specification
    targets: list[str] = field(default_factory=list)  # IPs, CIDRs, ranges
    ports: list[int] = field(default_factory=lambda: [22, 3389])

    # Timing
    timeout: float = 3.0  # Connection timeout in seconds
    max_concurrent: int = 100  # Max concurrent connections
    delay_between_hosts: float = 0.0  # Delay between hosts (rate limiting)

    # Features
    grab_banner: bool = True
    fingerprint: bool = True

    # Credential testing (requires explicit opt-in)
    test_credentials: bool = False
    usernames: list[str] = field(default_factory=list)
    passwords: list[str] = field(default_factory=list)
    stop_on_valid: bool = True  # Stop testing after first valid credential


@dataclass
class ScanStats:
    """Statistics for a scan operation."""

    total_targets: int = 0
    scanned: int = 0
    open_ports: int = 0
    ssh_found: int = 0
    rdp_found: int = 0
    credentials_valid: int = 0
    errors: int = 0
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def duration(self) -> float:
        """Get scan duration in seconds."""
        if self.end_time > 0:
            return self.end_time - self.start_time
        elif self.start_time > 0:
            return time.time() - self.start_time
        return 0.0

    @property
    def rate(self) -> float:
        """Get scan rate (hosts/second)."""
        duration = self.duration
        return self.scanned / duration if duration > 0 else 0.0


class NetworkScanner:
    """
    Async network scanner for SSH/RDP discovery.

    Features:
    - Fast async port scanning
    - Banner grabbing and fingerprinting
    - SSH version detection
    - RDP protocol detection
    - Optional credential testing

    Usage:
        scanner = NetworkScanner(
            on_result=lambda r: print(f"Found: {r.ip}:{r.port}"),
            on_progress=lambda s: print(f"Scanned: {s.scanned}/{s.total_targets}"),
        )
        results = await scanner.scan(config)
    """

    def __init__(
        self,
        on_result: Callable[[ScanResult], None] | None = None,
        on_progress: Callable[[ScanStats], None] | None = None,
        on_log: Callable[[str], None] | None = None,
    ):
        """
        Initialize NetworkScanner.

        Args:
            on_result: Callback for each scan result
            on_progress: Callback for progress updates
            on_log: Callback for log messages
        """
        self.on_result = on_result
        self.on_progress = on_progress
        self.on_log = on_log

        self._running = False
        self._stats = ScanStats()
        self._semaphore: asyncio.Semaphore | None = None
        self._results: list[ScanResult] = []

        self.logger = logging.getLogger(__name__)

    def _log(self, message: str) -> None:
        """Log a message."""
        self.logger.info(message)
        if self.on_log:
            self.on_log(message)

    async def scan(self, config: ScanConfig) -> list[ScanResult]:
        """
        Run a network scan.

        Args:
            config: Scan configuration

        Returns:
            List of scan results
        """
        if self._running:
            self._log("Scan already running")
            return []

        self._running = True
        self._results = []
        self._stats = ScanStats(start_time=time.time())

        # Parse targets into IP list
        targets = self._parse_targets(config.targets)
        self._stats.total_targets = len(targets) * len(config.ports)

        self._log(
            f"Starting scan: {len(targets)} hosts, {len(config.ports)} ports, "
            f"{self._stats.total_targets} total checks"
        )

        # Create semaphore for concurrency control
        self._semaphore = asyncio.Semaphore(config.max_concurrent)

        try:
            # Create scan tasks
            tasks = []
            for ip in targets:
                for port in config.ports:
                    task = asyncio.create_task(
                        self._scan_host(ip, port, config)
                    )
                    tasks.append(task)

                    # Rate limiting
                    if config.delay_between_hosts > 0:
                        await asyncio.sleep(config.delay_between_hosts)

            # Wait for all tasks
            await asyncio.gather(*tasks, return_exceptions=True)

        except asyncio.CancelledError:
            self._log("Scan cancelled")
        except Exception as e:
            self._log(f"Scan error: {e}")
            self.logger.error(f"Scan error: {e}", exc_info=True)
        finally:
            self._running = False
            self._stats.end_time = time.time()

        self._log(
            f"Scan complete: {self._stats.open_ports} open, "
            f"{self._stats.ssh_found} SSH, {self._stats.rdp_found} RDP, "
            f"{self._stats.duration:.1f}s"
        )

        return self._results

    def stop(self) -> None:
        """Stop the current scan."""
        self._running = False

    def _parse_targets(self, targets: list[str]) -> list[str]:
        """
        Parse target specifications into IP addresses.

        Supports:
        - Single IPs: "192.168.1.1"
        - CIDR notation: "192.168.1.0/24"
        - IP ranges: "192.168.1.1-254"
        """
        ips = []

        for target in targets:
            target = target.strip()
            if not target:
                continue

            try:
                # Try CIDR notation
                if "/" in target:
                    network = ipaddress.ip_network(target, strict=False)
                    ips.extend(str(ip) for ip in network.hosts())

                # Try IP range (e.g., "192.168.1.1-254")
                elif "-" in target:
                    parts = target.split("-")
                    if len(parts) == 2:
                        base_ip = parts[0].rsplit(".", 1)
                        if len(base_ip) == 2:
                            base = base_ip[0]
                            start = int(base_ip[1])
                            end = int(parts[1])
                            for i in range(start, end + 1):
                                ips.append(f"{base}.{i}")

                # Single IP
                else:
                    ipaddress.ip_address(target)  # Validate
                    ips.append(target)

            except ValueError as e:
                self._log(f"Invalid target '{target}': {e}")

        return ips

    async def _scan_host(
        self, ip: str, port: int, config: ScanConfig
    ) -> ScanResult | None:
        """Scan a single host/port."""
        if not self._running:
            return None

        async with self._semaphore:
            start_time = time.time()
            result = ScanResult(ip=ip, port=port, status=ScanStatus.CLOSED)

            try:
                # TCP connect scan
                conn = asyncio.open_connection(ip, port)
                reader, writer = await asyncio.wait_for(
                    conn, timeout=config.timeout
                )

                result.status = ScanStatus.OPEN
                result.scan_time = time.time() - start_time

                # Identify service
                if port == 22:
                    result.service = ServiceType.SSH
                    if config.grab_banner or config.fingerprint:
                        await self._grab_ssh_banner(reader, writer, result)
                elif port == 3389:
                    result.service = ServiceType.RDP
                    if config.fingerprint:
                        await self._detect_rdp(reader, writer, result)
                else:
                    # Generic banner grab
                    if config.grab_banner:
                        await self._grab_generic_banner(reader, result)

                # Close connection
                writer.close()
                await writer.wait_closed()

                # Credential testing (if enabled and service supports it)
                if (
                    config.test_credentials
                    and result.service == ServiceType.SSH
                    and config.usernames
                    and config.passwords
                ):
                    await self._test_ssh_credentials(ip, port, config, result)

            except asyncio.TimeoutError:
                result.status = ScanStatus.FILTERED
                result.error = "Connection timeout"
            except ConnectionRefusedError:
                result.status = ScanStatus.CLOSED
            except OSError as e:
                result.status = ScanStatus.ERROR
                result.error = str(e)
            except Exception as e:
                result.status = ScanStatus.ERROR
                result.error = str(e)
                self.logger.debug(f"Scan error for {ip}:{port}: {e}")

            # Update stats
            self._stats.scanned += 1
            if result.status == ScanStatus.OPEN:
                self._stats.open_ports += 1
                if result.service == ServiceType.SSH:
                    self._stats.ssh_found += 1
                elif result.service == ServiceType.RDP:
                    self._stats.rdp_found += 1
            if result.status == ScanStatus.ERROR:
                self._stats.errors += 1

            # Store result (only open ports or errors)
            if result.status in (ScanStatus.OPEN, ScanStatus.ERROR):
                self._results.append(result)
                if self.on_result:
                    self.on_result(result)

            # Progress callback
            if self.on_progress and self._stats.scanned % 100 == 0:
                self.on_progress(self._stats)

            return result

    async def _grab_ssh_banner(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        result: ScanResult,
    ) -> None:
        """Grab SSH banner and extract version info."""
        try:
            # SSH servers send their version on connect
            banner = await asyncio.wait_for(reader.readline(), timeout=2.0)
            banner_str = banner.decode("utf-8", errors="ignore").strip()
            result.banner = banner_str

            # Parse SSH version (e.g., "SSH-2.0-OpenSSH_8.9p1 Ubuntu-3")
            if banner_str.startswith("SSH-"):
                parts = banner_str.split("-", 2)
                if len(parts) >= 3:
                    result.version = parts[2]
                    result.fingerprint = f"SSH-{parts[1]}"

        except Exception as e:
            self.logger.debug(f"SSH banner grab failed: {e}")

    async def _detect_rdp(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        result: ScanResult,
    ) -> None:
        """
        Detect RDP service using TPKT/X.224 Connection Request.

        RDP uses TPKT (RFC 1006) encapsulation over TCP.
        """
        try:
            # TPKT header + X.224 Connection Request
            # This is a minimal RDP connection request
            tpkt_x224 = bytes([
                # TPKT Header (4 bytes)
                0x03,  # Version
                0x00,  # Reserved
                0x00, 0x13,  # Length (19 bytes total)
                # X.224 Connection Request (15 bytes)
                0x0e,  # Length indicator
                0xe0,  # Connection Request
                0x00, 0x00,  # Destination reference
                0x00, 0x00,  # Source reference
                0x00,  # Class/options
                # Cookie (empty)
                0x01, 0x00, 0x08, 0x00,  # RDP Negotiation Request
                0x00, 0x00, 0x00, 0x00,
            ])

            writer.write(tpkt_x224)
            await writer.drain()

            # Read response
            response = await asyncio.wait_for(reader.read(19), timeout=2.0)

            # Check for valid TPKT response
            if len(response) >= 4 and response[0] == 0x03:
                result.fingerprint = "RDP/TPKT"

                # Check X.224 response type
                if len(response) >= 6:
                    x224_type = response[5]
                    if x224_type == 0xd0:  # Connection Confirm
                        result.banner = "RDP Connection Confirm"
                    elif x224_type == 0xe0:  # Connection Request (echo)
                        result.banner = "RDP echo"

        except Exception as e:
            self.logger.debug(f"RDP detection failed: {e}")

    async def _grab_generic_banner(
        self, reader: asyncio.StreamReader, result: ScanResult
    ) -> None:
        """Grab generic banner from service."""
        try:
            banner = await asyncio.wait_for(reader.read(1024), timeout=2.0)
            result.banner = banner.decode("utf-8", errors="ignore").strip()[:256]
        except Exception:
            pass

    async def _test_ssh_credentials(
        self,
        ip: str,
        port: int,
        config: ScanConfig,
        result: ScanResult,
    ) -> None:
        """
        Test SSH credentials.

        IMPORTANT: Only use with explicit authorization.
        """
        if not ASYNCSSH_AVAILABLE:
            self._log("asyncssh not installed - skipping credential testing")
            return

        for username in config.usernames:
            for password in config.passwords:
                if not self._running:
                    return

                try:
                    # Attempt SSH connection
                    async with asyncssh.connect(
                        ip,
                        port=port,
                        username=username,
                        password=password,
                        known_hosts=None,
                        connect_timeout=config.timeout,
                    ):
                        # Success!
                        result.credential_status = CredentialStatus.VALID
                        result.valid_username = username
                        result.valid_password = password
                        self._stats.credentials_valid += 1

                        self._log(f"Valid credentials found: {ip}:{port}")

                        if config.stop_on_valid:
                            return

                except asyncssh.PermissionDenied:
                    # Invalid credentials - continue testing
                    continue
                except Exception as e:
                    # Connection error - stop testing this host
                    result.credential_status = CredentialStatus.ERROR
                    self.logger.debug(f"Credential test error: {e}")
                    return

        # No valid credentials found
        if result.credential_status == CredentialStatus.NOT_TESTED:
            result.credential_status = CredentialStatus.INVALID

    @property
    def is_running(self) -> bool:
        """Check if scan is running."""
        return self._running

    @property
    def stats(self) -> ScanStats:
        """Get current scan statistics."""
        return self._stats


# Utility function for simple scans
async def quick_scan(
    targets: list[str],
    ports: list[int] | None = None,
    timeout: float = 3.0,
    max_concurrent: int = 100,
) -> list[ScanResult]:
    """
    Perform a quick network scan.

    Args:
        targets: List of target IPs, CIDRs, or ranges
        ports: Ports to scan (default: [22, 3389])
        timeout: Connection timeout
        max_concurrent: Max concurrent connections

    Returns:
        List of scan results
    """
    config = ScanConfig(
        targets=targets,
        ports=ports or [22, 3389],
        timeout=timeout,
        max_concurrent=max_concurrent,
        grab_banner=True,
        fingerprint=True,
        test_credentials=False,
    )

    scanner = NetworkScanner()
    return await scanner.scan(config)
