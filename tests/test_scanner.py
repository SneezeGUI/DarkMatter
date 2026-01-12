"""Tests for NetworkScanner module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.scanner import (
    CredentialStatus,
    NetworkScanner,
    ScanConfig,
    ScanResult,
    ScanStats,
    ScanStatus,
    ServiceType,
)


class TestEnums:
    """Test enum classes."""

    def test_service_type_values(self):
        """Test ServiceType enum values."""
        assert ServiceType.SSH.value == "ssh"
        assert ServiceType.RDP.value == "rdp"
        assert ServiceType.UNKNOWN.value == "unknown"

    def test_scan_status_values(self):
        """Test ScanStatus enum values."""
        assert ScanStatus.OPEN.value == "open"
        assert ScanStatus.CLOSED.value == "closed"
        assert ScanStatus.FILTERED.value == "filtered"
        assert ScanStatus.ERROR.value == "error"

    def test_credential_status_values(self):
        """Test CredentialStatus enum values."""
        assert CredentialStatus.VALID.value == "valid"
        assert CredentialStatus.INVALID.value == "invalid"
        assert CredentialStatus.NOT_TESTED.value == "not_tested"
        assert CredentialStatus.ERROR.value == "error"


class TestScanResult:
    """Test ScanResult dataclass."""

    def test_scan_result_defaults(self):
        """Test ScanResult default values."""
        result = ScanResult(
            ip="192.168.1.1",
            port=22,
            status=ScanStatus.OPEN,
        )
        assert result.ip == "192.168.1.1"
        assert result.port == 22
        assert result.status == ScanStatus.OPEN
        assert result.service == ServiceType.UNKNOWN
        assert result.banner == ""
        assert result.fingerprint == ""
        assert result.version == ""
        assert result.scan_time == 0.0
        assert result.error == ""
        assert result.credential_status == CredentialStatus.NOT_TESTED
        assert result.valid_username == ""
        assert result.valid_password == ""

    def test_scan_result_with_all_fields(self):
        """Test ScanResult with all fields populated."""
        result = ScanResult(
            ip="10.0.0.1",
            port=22,
            status=ScanStatus.OPEN,
            service=ServiceType.SSH,
            banner="SSH-2.0-OpenSSH_8.9p1",
            fingerprint="SSH-2.0",
            version="OpenSSH_8.9p1",
            scan_time=0.15,
            credential_status=CredentialStatus.VALID,
            valid_username="admin",
            valid_password="password123",
        )
        assert result.service == ServiceType.SSH
        assert result.banner == "SSH-2.0-OpenSSH_8.9p1"
        assert result.credential_status == CredentialStatus.VALID
        assert result.valid_username == "admin"


class TestScanConfig:
    """Test ScanConfig dataclass."""

    def test_scan_config_defaults(self):
        """Test ScanConfig default values."""
        config = ScanConfig()
        assert config.targets == []
        assert config.ports == [22, 3389]
        assert config.timeout == 3.0
        assert config.max_concurrent == 100
        assert config.delay_between_hosts == 0.0
        assert config.grab_banner is True
        assert config.fingerprint is True
        assert config.test_credentials is False
        assert config.usernames == []
        assert config.passwords == []
        assert config.stop_on_valid is True

    def test_scan_config_custom_values(self):
        """Test ScanConfig with custom values."""
        config = ScanConfig(
            targets=["192.168.1.0/24"],
            ports=[22, 2222, 3389],
            timeout=5.0,
            max_concurrent=50,
            test_credentials=True,
            usernames=["root", "admin"],
            passwords=["password", "admin"],
        )
        assert config.targets == ["192.168.1.0/24"]
        assert config.ports == [22, 2222, 3389]
        assert config.timeout == 5.0
        assert config.max_concurrent == 50
        assert config.test_credentials is True
        assert len(config.usernames) == 2
        assert len(config.passwords) == 2


class TestScanStats:
    """Test ScanStats dataclass."""

    def test_scan_stats_defaults(self):
        """Test ScanStats default values."""
        stats = ScanStats()
        assert stats.total_targets == 0
        assert stats.scanned == 0
        assert stats.open_ports == 0
        assert stats.ssh_found == 0
        assert stats.rdp_found == 0
        assert stats.credentials_valid == 0
        assert stats.errors == 0
        assert stats.start_time == 0.0
        assert stats.end_time == 0.0

    def test_scan_stats_duration_completed(self):
        """Test duration property when scan is completed."""
        stats = ScanStats(start_time=100.0, end_time=110.0)
        assert stats.duration == 10.0

    def test_scan_stats_duration_in_progress(self):
        """Test duration property when scan is in progress."""
        import time

        start = time.time()
        stats = ScanStats(start_time=start, end_time=0.0)
        # Duration should be close to 0 since we just started
        assert 0 <= stats.duration < 1

    def test_scan_stats_duration_not_started(self):
        """Test duration property when scan not started."""
        stats = ScanStats()
        assert stats.duration == 0.0

    def test_scan_stats_rate(self):
        """Test rate property."""
        stats = ScanStats(scanned=100, start_time=0.0, end_time=10.0)
        assert stats.rate == 10.0

    def test_scan_stats_rate_zero_duration(self):
        """Test rate property with zero duration."""
        stats = ScanStats(scanned=100)
        assert stats.rate == 0.0


class TestNetworkScannerInit:
    """Test NetworkScanner initialization."""

    def test_scanner_init_defaults(self):
        """Test scanner initialization with defaults."""
        scanner = NetworkScanner()
        assert scanner.on_result is None
        assert scanner.on_progress is None
        assert scanner.on_log is None
        assert not scanner.is_running
        assert scanner.stats.total_targets == 0

    def test_scanner_init_with_callbacks(self):
        """Test scanner initialization with callbacks."""
        on_result = MagicMock()
        on_progress = MagicMock()
        on_log = MagicMock()

        scanner = NetworkScanner(
            on_result=on_result,
            on_progress=on_progress,
            on_log=on_log,
        )

        assert scanner.on_result == on_result
        assert scanner.on_progress == on_progress
        assert scanner.on_log == on_log


class TestTargetParsing:
    """Test target parsing functionality."""

    def test_parse_single_ip(self):
        """Test parsing single IP address."""
        scanner = NetworkScanner()
        ips = scanner._parse_targets(["192.168.1.1"])
        assert ips == ["192.168.1.1"]

    def test_parse_multiple_ips(self):
        """Test parsing multiple IP addresses."""
        scanner = NetworkScanner()
        ips = scanner._parse_targets(["192.168.1.1", "192.168.1.2"])
        assert len(ips) == 2
        assert "192.168.1.1" in ips
        assert "192.168.1.2" in ips

    def test_parse_cidr_notation(self):
        """Test parsing CIDR notation."""
        scanner = NetworkScanner()
        ips = scanner._parse_targets(["192.168.1.0/30"])
        # /30 gives 4 addresses, minus network and broadcast = 2 hosts
        assert len(ips) == 2
        assert "192.168.1.1" in ips
        assert "192.168.1.2" in ips

    def test_parse_ip_range(self):
        """Test parsing IP range notation."""
        scanner = NetworkScanner()
        ips = scanner._parse_targets(["192.168.1.1-3"])
        assert len(ips) == 3
        assert "192.168.1.1" in ips
        assert "192.168.1.2" in ips
        assert "192.168.1.3" in ips

    def test_parse_invalid_target(self):
        """Test parsing invalid target."""
        scanner = NetworkScanner()
        ips = scanner._parse_targets(["not_an_ip"])
        assert ips == []

    def test_parse_empty_target(self):
        """Test parsing empty target list."""
        scanner = NetworkScanner()
        ips = scanner._parse_targets([])
        assert ips == []

    def test_parse_whitespace_target(self):
        """Test parsing target with whitespace."""
        scanner = NetworkScanner()
        ips = scanner._parse_targets(["  192.168.1.1  "])
        assert ips == ["192.168.1.1"]

    def test_parse_mixed_targets(self):
        """Test parsing mixed target types."""
        scanner = NetworkScanner()
        ips = scanner._parse_targets([
            "192.168.1.1",
            "10.0.0.0/30",
            "172.16.0.1-2",
        ])
        assert "192.168.1.1" in ips
        assert "10.0.0.1" in ips
        assert "10.0.0.2" in ips
        assert "172.16.0.1" in ips
        assert "172.16.0.2" in ips


class TestScannerProperties:
    """Test scanner properties."""

    def test_is_running_property(self):
        """Test is_running property."""
        scanner = NetworkScanner()
        assert scanner.is_running is False

    def test_stats_property(self):
        """Test stats property."""
        scanner = NetworkScanner()
        stats = scanner.stats
        assert isinstance(stats, ScanStats)

    def test_stop_method(self):
        """Test stop method sets running to False."""
        scanner = NetworkScanner()
        scanner._running = True
        scanner.stop()
        assert scanner._running is False


class TestScanOperations:
    """Test scan operations."""

    @pytest.mark.asyncio
    async def test_scan_already_running(self):
        """Test scan returns empty when already running."""
        scanner = NetworkScanner()
        scanner._running = True

        config = ScanConfig(targets=["192.168.1.1"])
        results = await scanner.scan(config)

        assert results == []

    @pytest.mark.asyncio
    async def test_scan_with_no_targets(self):
        """Test scan with no targets."""
        scanner = NetworkScanner()
        config = ScanConfig(targets=[])
        results = await scanner.scan(config)

        assert results == []
        assert scanner.stats.total_targets == 0

    @pytest.mark.asyncio
    async def test_scan_host_closed_port(self):
        """Test scanning a closed port."""
        scanner = NetworkScanner()
        scanner._running = True
        scanner._semaphore = asyncio.Semaphore(10)

        with patch("asyncio.open_connection") as mock_open:
            mock_open.side_effect = ConnectionRefusedError()

            config = ScanConfig(
                targets=["127.0.0.1"],
                ports=[9999],
                timeout=1.0,
            )

            result = await scanner._scan_host("127.0.0.1", 9999, config)

            assert result.status == ScanStatus.CLOSED

    @pytest.mark.asyncio
    async def test_scan_host_timeout(self):
        """Test scanning with timeout."""
        scanner = NetworkScanner()
        scanner._running = True
        scanner._semaphore = asyncio.Semaphore(10)

        with patch("asyncio.open_connection") as mock_open:
            mock_open.side_effect = asyncio.TimeoutError()

            config = ScanConfig(
                targets=["192.168.1.1"],
                ports=[22],
                timeout=0.1,
            )

            result = await scanner._scan_host("192.168.1.1", 22, config)

            assert result.status == ScanStatus.FILTERED
            assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_scan_host_os_error(self):
        """Test scanning with OS error."""
        scanner = NetworkScanner()
        scanner._running = True
        scanner._semaphore = asyncio.Semaphore(10)

        with patch("asyncio.open_connection") as mock_open:
            mock_open.side_effect = OSError("Network unreachable")

            config = ScanConfig(
                targets=["192.168.1.1"],
                ports=[22],
                timeout=1.0,
            )

            result = await scanner._scan_host("192.168.1.1", 22, config)

            assert result.status == ScanStatus.ERROR
            assert "unreachable" in result.error.lower()


class TestBannerGrabbing:
    """Test banner grabbing functionality."""

    @pytest.mark.asyncio
    async def test_grab_ssh_banner(self):
        """Test SSH banner grabbing."""
        scanner = NetworkScanner()

        mock_reader = AsyncMock()
        mock_reader.readline.return_value = b"SSH-2.0-OpenSSH_8.9p1 Ubuntu-3\n"

        mock_writer = MagicMock()

        result = ScanResult(ip="192.168.1.1", port=22, status=ScanStatus.OPEN)

        await scanner._grab_ssh_banner(mock_reader, mock_writer, result)

        assert result.banner == "SSH-2.0-OpenSSH_8.9p1 Ubuntu-3"
        assert result.version == "OpenSSH_8.9p1 Ubuntu-3"
        assert result.fingerprint == "SSH-2.0"

    @pytest.mark.asyncio
    async def test_grab_ssh_banner_timeout(self):
        """Test SSH banner grabbing with timeout."""
        scanner = NetworkScanner()

        mock_reader = AsyncMock()
        mock_reader.readline.side_effect = asyncio.TimeoutError()

        mock_writer = MagicMock()

        result = ScanResult(ip="192.168.1.1", port=22, status=ScanStatus.OPEN)

        await scanner._grab_ssh_banner(mock_reader, mock_writer, result)

        # Should not crash, just leave banner empty
        assert result.banner == ""


class TestRDPDetection:
    """Test RDP detection functionality."""

    @pytest.mark.asyncio
    async def test_detect_rdp_success(self):
        """Test successful RDP detection."""
        scanner = NetworkScanner()

        # Mock valid TPKT response
        mock_reader = AsyncMock()
        mock_reader.read.return_value = bytes([
            0x03, 0x00, 0x00, 0x13,  # TPKT header
            0x0e, 0xd0,  # X.224 Connection Confirm
            0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00,
        ])

        mock_writer = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.write = MagicMock()

        result = ScanResult(ip="192.168.1.1", port=3389, status=ScanStatus.OPEN)

        await scanner._detect_rdp(mock_reader, mock_writer, result)

        assert result.fingerprint == "RDP/TPKT"
        assert "RDP" in result.banner

    @pytest.mark.asyncio
    async def test_detect_rdp_timeout(self):
        """Test RDP detection with timeout."""
        scanner = NetworkScanner()

        mock_reader = AsyncMock()
        mock_reader.read.side_effect = asyncio.TimeoutError()

        mock_writer = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.write = MagicMock()

        result = ScanResult(ip="192.168.1.1", port=3389, status=ScanStatus.OPEN)

        await scanner._detect_rdp(mock_reader, mock_writer, result)

        # Should not crash
        assert result.fingerprint == ""


class TestGenericBanner:
    """Test generic banner grabbing."""

    @pytest.mark.asyncio
    async def test_grab_generic_banner(self):
        """Test generic banner grabbing."""
        scanner = NetworkScanner()

        mock_reader = AsyncMock()
        mock_reader.read.return_value = b"Welcome to server\n"

        result = ScanResult(ip="192.168.1.1", port=8080, status=ScanStatus.OPEN)

        await scanner._grab_generic_banner(mock_reader, result)

        assert result.banner == "Welcome to server"

    @pytest.mark.asyncio
    async def test_grab_generic_banner_truncation(self):
        """Test generic banner truncation for long banners."""
        scanner = NetworkScanner()

        mock_reader = AsyncMock()
        mock_reader.read.return_value = b"A" * 500

        result = ScanResult(ip="192.168.1.1", port=8080, status=ScanStatus.OPEN)

        await scanner._grab_generic_banner(mock_reader, result)

        assert len(result.banner) == 256


class TestCallbacks:
    """Test callback invocations."""

    @pytest.mark.asyncio
    async def test_on_result_callback(self):
        """Test on_result callback is invoked."""
        results = []
        scanner = NetworkScanner(on_result=lambda r: results.append(r))

        with patch("asyncio.open_connection") as mock_open:
            mock_open.side_effect = ConnectionRefusedError()

            config = ScanConfig(targets=["127.0.0.1"], ports=[9999])
            await scanner.scan(config)

        # Closed ports don't trigger on_result (only open or error)
        assert len(results) == 0

    def test_log_callback(self):
        """Test log callback is invoked."""
        logs = []
        scanner = NetworkScanner(on_log=lambda msg: logs.append(msg))

        scanner._log("Test message")

        assert "Test message" in logs
