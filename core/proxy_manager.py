import logging
import os
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import requests as std_requests
from curl_cffi import requests

from .constants import (
    DEAD_PROXY_SPEED_MS,
    PROXY_CHECK_BATCH_SIZE,
    SCRAPE_TIMEOUT_SECONDS,
)
from .header_manager import HeaderManager
from .models import ProxyCheckResult, ProxyConfig
from .source_health_tracker import SourceHealthTracker
from .validators import (
    Validator,
    ValidatorResult,
    aggregate_results,
)

# GeoIP cache to avoid repeated lookups
_geoip_cache: dict[str, dict] = {}

# MaxMind GeoLite2 database reader (lazy loaded)
_geoip_reader = None
_geoip_reader_initialized = False


def _init_geoip_reader():
    """
    Initialize the MaxMind GeoLite2-City database reader.
    Returns the reader or None if unavailable.
    """
    global _geoip_reader, _geoip_reader_initialized

    if _geoip_reader_initialized:
        return _geoip_reader

    _geoip_reader_initialized = True

    # Try to find the database file
    db_paths = [
        os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "resources",
            "GeoLite2-City.mmdb",
        ),
        os.path.join(
            os.path.dirname(__file__), "..", "resources", "GeoLite2-City.mmdb"
        ),
        "resources/GeoLite2-City.mmdb",
        "GeoLite2-City.mmdb",
    ]

    db_path = None
    for path in db_paths:
        if os.path.exists(path):
            db_path = path
            break

    if not db_path:
        logging.info("GeoLite2-City.mmdb not found, will use API fallback for GeoIP")
        return None

    try:
        import geoip2.database

        _geoip_reader = geoip2.database.Reader(db_path)
        logging.info(f"GeoLite2-City database loaded from {db_path}")
        return _geoip_reader
    except ImportError:
        logging.warning(
            "geoip2 package not installed, will use API fallback. Run: pip install geoip2"
        )
        return None
    except Exception as e:
        logging.warning(f"Failed to load GeoLite2 database: {e}")
        return None


def _lookup_geoip_local(ip: str) -> dict | None:
    """
    Look up geographic information using local MaxMind database.
    Returns dict or None if lookup fails.
    """
    reader = _init_geoip_reader()
    if not reader:
        return None

    try:
        response = reader.city(ip)
        return {
            "country": response.country.name or "Unknown",
            "countryCode": response.country.iso_code or "??",
            "city": response.city.name or "",
        }
    except Exception as e:
        # IP not found in database or other error (e.g., private IP ranges)
        logging.debug(f"GeoIP local lookup failed for {ip}: {type(e).__name__}")
        return None


def _lookup_geoip_api(ip: str) -> dict:
    """
    Look up geographic information using multiple API fallbacks.
    Tries multiple providers in sequence until one succeeds.
    Returns dict with country, countryCode, city.
    """
    default = {"country": "Unknown", "countryCode": "??", "city": ""}

    # Validate IP format (basic check)
    if not ip or ip in ("0.0.0.0", "127.0.0.1", "localhost"):
        return default

    # API 1: ip-api.com (free, 45 req/min) - HTTP only, fast
    try:
        resp = std_requests.get(
            f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,city",
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                logging.debug(
                    f"GeoIP ip-api.com success for {ip}: {data.get('country')}"
                )
                return {
                    "country": data.get("country", "Unknown"),
                    "countryCode": data.get("countryCode", "??"),
                    "city": data.get("city", ""),
                }
            else:
                logging.debug(
                    f"GeoIP ip-api.com returned status: {data.get('status')} for {ip}"
                )
        else:
            logging.debug(f"GeoIP ip-api.com HTTP {resp.status_code} for {ip}")
    except Exception as e:
        logging.debug(f"GeoIP ip-api.com failed for {ip}: {type(e).__name__}: {e}")

    # API 2: ipapi.co (free, 1000 req/day)
    try:
        resp = std_requests.get(
            f"https://ipapi.co/{ip}/json/",
            timeout=5,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
            },
        )
        if resp.status_code == 200:
            data = resp.json()
            if not data.get("error"):
                logging.debug(
                    f"GeoIP ipapi.co success for {ip}: {data.get('country_name')}"
                )
                return {
                    "country": data.get("country_name", "Unknown"),
                    "countryCode": data.get("country_code", "??"),
                    "city": data.get("city", ""),
                }
            else:
                logging.debug(f"GeoIP ipapi.co error: {data.get('reason')} for {ip}")
        else:
            logging.debug(f"GeoIP ipapi.co HTTP {resp.status_code} for {ip}")
    except Exception as e:
        logging.debug(f"GeoIP ipapi.co failed for {ip}: {type(e).__name__}: {e}")

    # API 3: ipwhois.app (free, 10000 req/month)
    try:
        resp = std_requests.get(f"https://ipwhois.app/json/{ip}", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success", True):  # ipwhois returns success=false on error
                logging.debug(
                    f"GeoIP ipwhois.app success for {ip}: {data.get('country')}"
                )
                return {
                    "country": data.get("country", "Unknown"),
                    "countryCode": data.get("country_code", "??"),
                    "city": data.get("city", ""),
                }
            else:
                logging.debug(f"GeoIP ipwhois.app returned success=false for {ip}")
        else:
            logging.debug(f"GeoIP ipwhois.app HTTP {resp.status_code} for {ip}")
    except Exception as e:
        logging.debug(f"GeoIP ipwhois.app failed for {ip}: {type(e).__name__}: {e}")

    logging.warning(f"All GeoIP APIs failed for {ip}")
    return default


def lookup_geoip(ip: str) -> dict:
    """
    Look up geographic information for an IP address.

    Uses local MaxMind GeoLite2-City database for speed and no rate limits.
    Falls back to ip-api.com if database is unavailable.

    Results are cached to avoid repeated lookups.

    Returns dict with: country, countryCode, city
    """
    global _geoip_cache

    if ip in _geoip_cache:
        return _geoip_cache[ip]

    # Try local database first (fast, no rate limit)
    result = _lookup_geoip_local(ip)

    if result:
        logging.debug(f"GeoIP local DB success for {ip}: {result.get('country')}")
    else:
        # Fall back to API if local lookup failed
        logging.debug(f"GeoIP local DB miss for {ip}, trying API fallback")
        result = _lookup_geoip_api(ip)

    _geoip_cache[ip] = result
    return result


class ThreadedProxyManager:
    def __init__(self):
        self.regex_pattern = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b")
        self.health_tracker = SourceHealthTracker()

    def scrape(
        self,
        sources: list[str],
        protocols: list[str],
        max_threads: int = 20,
        scraper_proxy: str = None,
        on_progress: Callable[[int], None] = None,
    ) -> list[ProxyConfig]:
        """Scrapes proxies from provided source URLs using threads."""
        found_proxies_map: dict[tuple, str] = {}
        lock = logging.threading.Lock()

        def fetch_source(url: str):
            try:
                # Use standard requests for speed (scraping text/html usually doesn't need TLS fingerprinting)
                # But we use rotating headers to avoid 403s
                h = HeaderManager.get_random_headers()
                proxies = (
                    {"http": scraper_proxy, "https": scraper_proxy}
                    if scraper_proxy
                    else None
                )

                response = std_requests.get(
                    url, timeout=SCRAPE_TIMEOUT_SECONDS, headers=h, proxies=proxies
                )

                proxies_found_in_source = 0

                if response.status_code == 200:
                    if on_progress:
                        on_progress(len(response.content))
                    matches = self.regex_pattern.findall(response.text)

                    # Smart Protocol Detection
                    u_lower = url.lower()
                    source_protos = []

                    # Heuristics based on URL hints
                    if "socks5" in u_lower:
                        source_protos.append("socks5")
                    if "socks4" in u_lower:
                        source_protos.append("socks4")
                    if "http" in u_lower and "socks" not in u_lower:
                        source_protos.append("http")

                    # Intersect with user requests
                    valid_protos = [p for p in source_protos if p in protocols]

                    # Fallback: If no specific protocol detected, try all requested
                    if not valid_protos:
                        valid_protos = protocols

                    for m in matches:
                        ip, port = m.split(":")
                        for proto in valid_protos:
                            key = (ip, int(port), proto)
                            with lock:
                                if key not in found_proxies_map:
                                    found_proxies_map[key] = url
                                    proxies_found_in_source += 1

                # Record scraping stats for this source
                self.health_tracker.record_check(
                    url,
                    scraped=proxies_found_in_source,
                    alive=0,
                    dead=0,
                    avg_score=0.0,
                    avg_speed=0.0
                )

            except Exception as e:
                logging.debug(f"Error scraping {url}: {e}")

        with ThreadPoolExecutor(max_workers=max_threads) as ex:
            ex.map(
                fetch_source,
                [url for url in sources if url.strip() and not url.startswith("#")],
            )

        results = []
        for (ip, port, proto), source in found_proxies_map.items():
            results.append(ProxyConfig(host=ip, port=port, protocol=proto, source=source))

        return results

    def check_proxies(
        self,
        proxies: list[ProxyConfig],
        target_url: str,
        timeout_ms: int,
        real_ip: str,
        on_progress: Callable[[ProxyCheckResult, int, int], None],
        concurrency: int = 100,
        pause_checker: Callable[[], bool] | None = None,
        validators: list[Validator] | None = None,
        test_depth: str = "quick",
        system_proxy: str | None = None,
    ) -> list[ProxyCheckResult]:
        """
        Checks a list of proxies concurrently using threads.

        Args:
            system_proxy: Optional system proxy URL to route checking through (proxy chaining).
                         Format: "protocol://host:port" (e.g., "socks5://127.0.0.1:1080")
        """
        total = len(proxies)
        completed = 0
        lock = logging.threading.Lock()  # Simple lock for counter

        # Determine which validators to use based on test_depth
        active_validators = []
        if validators:
            enabled = [v for v in validators if v.enabled]
            if test_depth == "quick":
                active_validators = enabled[:1] if enabled else []
            elif test_depth == "normal":
                active_validators = enabled[:3] if enabled else []
            else:  # thorough
                active_validators = enabled

        def check_single(proxy: ProxyConfig):
            nonlocal completed

            # Pause logic
            if pause_checker:
                while pause_checker():
                    time.sleep(0.5)

            result = self._test_proxy(
                proxy, target_url, timeout_ms, real_ip, active_validators, system_proxy
            )

            with lock:
                completed += 1
                current_completed = completed

            if on_progress:
                on_progress(result, current_completed, total)

            if result.status == "Active":
                return result
            return None

        valid_results_list = []
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futures = []

            # Scale batch size with concurrency (min 50, max 500, ~10% of threads)
            batch_size = max(PROXY_CHECK_BATCH_SIZE, min(500, concurrency // 10))
            # Reduce sleep for high concurrency
            batch_sleep = (
                0.05 if concurrency <= 500 else 0.02 if concurrency <= 2000 else 0.01
            )

            # Staggered Launch to prevent UI freeze
            for i in range(0, len(proxies), batch_size):
                batch = proxies[i : i + batch_size]
                for p in batch:
                    futures.append(ex.submit(check_single, p))

                # Check pause during submission
                if pause_checker:
                    while pause_checker():
                        time.sleep(0.5)

                # Small sleep to yield CPU
                time.sleep(batch_sleep)

            for f in futures:
                res = f.result()
                if res:
                    valid_results_list.append(res)

        # Update source health stats
        self._update_source_health_from_checks(proxies, valid_results_list)

        return valid_results_list

    def _test_proxy_alive(
        self, proxy: ProxyConfig, target_url: str, timeout_ms: int, system_proxy: str | None = None
    ) -> ProxyCheckResult:
        """
        Phase 1: Quick alive check - tests connectivity, speed, type, and GeoIP.
        Does NOT run validator API checks (saves bandwidth for dead proxies).

        Args:
            system_proxy: Optional system proxy for proxy chaining. Routes the check through this proxy.
        """
        result = ProxyCheckResult(
            proxy=proxy,
            status="Dead",
            speed=DEAD_PROXY_SPEED_MS,
            type=proxy.protocol.upper(),
            country="Unknown",
            country_code="??",
            city="",
            anonymity="Unknown",  # Will be set in phase 2
        )

        proxy_url = proxy.to_curl_cffi_format()
        proxies_dict = {"http": proxy_url, "https": proxy_url}

        # TODO v3.7.0: Implement true proxy chaining for checking
        # Requires SOCKS5 nested proxy support: slave -> master_proxy -> test_proxy -> target
        # Current limitation: curl_cffi doesn't support nested proxies natively
        # For now, system_proxy is only used for scraping (which works correctly)
        if system_proxy:
            logging.info(
                "Note: system_proxy is currently only supported for scraping. "
                "Proxy checking tests proxies directly. "
                "Full proxy chaining will be implemented in v3.7.0 with SOCKS5 support."
            )

        timeout_sec = max(timeout_ms / 1000, 1.0)

        bytes_transferred = 0
        is_https = target_url.lower().startswith("https://")

        start_time = time.time()
        try:
            with requests.Session(impersonate="chrome120") as session:
                resp = session.get(
                    target_url, timeout=timeout_sec, proxies=proxies_dict, verify=False
                )

                latency = int((time.time() - start_time) * 1000)
                result.speed = latency
                result.status = "Active"

                # Calculate bytes transferred
                request_overhead = 500
                response_headers = 300
                response_body = len(resp.content) if resp.content else 0
                tls_overhead = 5000 if is_https else 0
                proxy_connect = 200 if is_https else 0
                bytes_transferred = (
                    request_overhead
                    + response_headers
                    + response_body
                    + tls_overhead
                    + proxy_connect
                )

                # Type detection
                if is_https and result.type == "HTTP":
                    result.type = "HTTPS"

                # HTTPS tunneling test for HTTP proxies
                if not is_https and result.type == "HTTP":
                    https_capable = self._test_https_tunnel(
                        session, proxies_dict, timeout_sec
                    )
                    if https_capable:
                        result.type = "HTTPS"
                        bytes_transferred += 2000
                        logging.debug(
                            f"Proxy {proxy.host}:{proxy.port} upgraded to HTTPS (tunnel test passed)"
                        )

                # Extract exit IP for GeoIP
                proxy_exit_ip = None
                try:
                    response_data = resp.json()
                    origin = response_data.get("origin", "")
                    if origin:
                        proxy_exit_ip = origin.split(",")[0].strip()
                        logging.debug(
                            f"Proxy {proxy.host}:{proxy.port} exit IP: {proxy_exit_ip}"
                        )
                    else:
                        logging.debug(
                            "JSON response missing 'origin' field. "
                            "Consider using a URL like https://httpbin.org/get"
                        )
                except (ValueError, KeyError, AttributeError, requests.exceptions.JSONDecodeError) as e:
                    # Non-JSON response is common during proxy testing (failures, error pages, etc.)
                    # Only log at debug level since fallback to proxy host IP works fine
                    logging.debug(
                        f"Test URL did not return valid JSON (expected during proxy failures). "
                        f"Falling back to proxy host IP for GeoIP. Error: {e}"
                    )

                # GeoIP lookup - try exit IP first, fallback to proxy host IP
                lookup_ip = proxy_exit_ip or proxy.host
                if lookup_ip:
                    geo = lookup_geoip(lookup_ip)
                    result.country = geo.get("country", "Unknown")
                    result.country_code = geo.get("countryCode", "??")
                    result.city = geo.get("city", "")
                    if result.country == "Unknown":
                        logging.debug(f"GeoIP lookup failed for {lookup_ip}")

                # Store exit IP for phase 2 validator checks
                result._exit_ip = proxy_exit_ip

                result.bytes_transferred = bytes_transferred

                # Base score (will be adjusted in phase 2 with anonymity factor)
                result.score = round(1000.0 / max(latency, 1), 2)
                proxy.score = result.score

        except Exception as e:
            logging.debug(
                f"Proxy {proxy.host}:{proxy.port} failed: {type(e).__name__}: {e}"
            )
            result.bytes_transferred = 1500 if is_https else 500

        return result

    def _test_proxy_anonymity(
        self,
        result: ProxyCheckResult,
        real_ip: str,
        timeout_ms: int,
        validators: list[Validator],
        system_proxy: str | None = None,
    ) -> ProxyCheckResult:
        """
        Phase 2: Anonymity check - runs validator API checks on confirmed-alive proxies.
        Only called for proxies that passed the alive check.

        Args:
            system_proxy: Optional system proxy for routing validator checks (proxy chaining)
        """
        if result.status != "Active":
            return result

        proxy = result.proxy
        proxy_url = proxy.to_curl_cffi_format()
        proxies_dict = {"http": proxy_url, "https": proxy_url}

        # Note: system_proxy parameter exists for future SOCKS5 chaining support
        # Currently ignored for anonymity checks (tests proxy directly)

        timeout_sec = max(timeout_ms / 1000, 1.0)

        proxy_exit_ip = getattr(result, "_exit_ip", None)
        bytes_transferred = result.bytes_transferred

        try:
            with requests.Session(impersonate="chrome120") as session:
                if validators and len(validators) > 0:
                    # Run multi-validator test
                    validator_results, validator_bytes = self._run_validators(
                        session, proxy, proxies_dict, validators, timeout_sec, real_ip
                    )
                    bytes_transferred += validator_bytes

                    aggregated = aggregate_results(
                        validator_results,
                        real_ip,
                        proxy_exit_ip=proxy_exit_ip or "",
                        proxy_worked=True,
                    )
                    result.anonymity = aggregated.anonymity_level
                    anon_score_factor = max(0.5, aggregated.anonymity_score / 100.0)
                else:
                    # Fallback to simple detection using IP comparison
                    if proxy_exit_ip and real_ip:
                        if proxy_exit_ip == real_ip:
                            result.anonymity = "Transparent"
                            anon_score_factor = 0.5
                        else:
                            result.anonymity = "Anonymous"
                            anon_score_factor = 1.0
                    else:
                        result.anonymity = "Anonymous"
                        anon_score_factor = 0.8

                # Update bytes and score with anonymity factor
                result.bytes_transferred = bytes_transferred
                base_score = 1000.0 / max(result.speed, 1)
                result.score = round(base_score * anon_score_factor, 2)
                proxy.score = result.score

        except Exception as e:
            logging.debug(
                f"Anonymity check failed for {proxy.host}:{proxy.port}: {type(e).__name__}: {e}"
            )
            # Keep the proxy as Active but with Unknown anonymity
            result.anonymity = "Unknown"

        return result

    def _test_proxy(
        self,
        proxy: ProxyConfig,
        target_url: str,
        timeout_ms: int,
        real_ip: str,
        validators: list[Validator] | None = None,
        system_proxy: str | None = None,
    ) -> ProxyCheckResult:
        """
        Full proxy test: Phase 1 (alive) + Phase 2 (anonymity) combined.
        Validators only run if proxy passes alive check.

        Args:
            system_proxy: Optional system proxy for proxy chaining (routes checking through this proxy)
        """
        # Phase 1: Quick alive check
        result = self._test_proxy_alive(proxy, target_url, timeout_ms, system_proxy)

        # Phase 2: Only check anonymity if proxy is alive
        if result.status == "Active" and validators:
            result = self._test_proxy_anonymity(result, real_ip, timeout_ms, validators, system_proxy)
        elif result.status == "Active":
            # No validators - use simple anonymity detection
            proxy_exit_ip = getattr(result, "_exit_ip", None)
            if proxy_exit_ip and real_ip:
                if proxy_exit_ip == real_ip:
                    result.anonymity = "Transparent"
                    anon_score_factor = 0.5
                else:
                    result.anonymity = "Anonymous"
                    anon_score_factor = 1.0
            else:
                result.anonymity = "Anonymous"
                anon_score_factor = 0.8

            # Adjust score with anonymity factor
            base_score = 1000.0 / max(result.speed, 1)
            result.score = round(base_score * anon_score_factor, 2)
            proxy.score = result.score

        return result

    def _run_validators(
        self,
        session,
        proxy: ProxyConfig,
        proxies_dict: dict,
        validators: list[Validator],
        timeout_sec: float,
        real_ip: str,
    ) -> tuple:
        """
        Run multiple validators against a proxy and collect results.
        Returns (List[ValidatorResult], total_bytes_transferred)
        """
        results = []
        total_bytes = 0

        for validator in validators:
            is_https = validator.url.lower().startswith("https://")
            try:
                start = time.time()
                resp = session.get(
                    validator.url,
                    timeout=min(timeout_sec, validator.timeout),
                    proxies=proxies_dict,
                    verify=False,
                )
                elapsed_ms = int((time.time() - start) * 1000)

                # Calculate bytes for this validator request
                request_overhead = 500
                response_headers = 300
                response_body = len(resp.content) if resp.content else 0
                # TLS overhead only for first HTTPS request in session (session reuse)
                # Subsequent HTTPS requests reuse connection, so minimal TLS overhead
                tls_overhead = (
                    500 if is_https else 0
                )  # Session reuse = smaller overhead
                total_bytes += (
                    request_overhead + response_headers + response_body + tls_overhead
                )

                vr = validator.parse_response(resp.text, resp.status_code, real_ip)
                vr.response_time_ms = elapsed_ms
                results.append(vr)

            except Exception as e:
                # Validator failed - record failure
                results.append(
                    ValidatorResult(
                        validator_name=validator.name, success=False, error=str(e)
                    )
                )
                # Failed request still used some bandwidth
                total_bytes += 800 if is_https else 300

        return results, total_bytes

    def _test_https_tunnel(
        self, session, proxies_dict: dict, timeout_sec: float
    ) -> bool:
        """
        Test if an HTTP proxy can tunnel HTTPS traffic (CONNECT method).

        This is critical for browser mode which requires HTTPS tunneling.
        HTTP proxies that can't tunnel HTTPS will fail on HTTPS sites.

        Uses a fast, reliable HTTPS endpoint for the test.

        Returns:
            True if proxy supports HTTPS tunneling, False otherwise
        """
        # Use a simple, fast HTTPS endpoint for the test
        # ipify is lightweight and reliable
        https_test_urls = [
            "https://api.ipify.org?format=json",
            "https://httpbin.org/ip",
        ]

        for test_url in https_test_urls:
            try:
                resp = session.get(
                    test_url,
                    timeout=min(timeout_sec, 5.0),  # Max 5s for quick test
                    proxies=proxies_dict,
                    verify=False,
                )
                if resp.status_code == 200:
                    return True
            except Exception:
                # Try next URL
                continue

        return False

    def _update_source_health_from_checks(
        self, all_proxies: list[ProxyConfig], active_results: list[ProxyCheckResult]
    ):
        """
        Aggregate check results by source and update health tracker.
        """
        if not self.health_tracker:
            return

        # Initialize counters per source
        source_stats = {}  # source -> {alive: 0, scores: [], speeds: []}

        # Count total proxies per source (to calculate dead count later)
        source_totals = {}
        for p in all_proxies:
            if not p.source:
                continue
            source_totals[p.source] = source_totals.get(p.source, 0) + 1
            if p.source not in source_stats:
                source_stats[p.source] = {"alive": 0, "scores": [], "speeds": []}

        # Process active results
        for res in active_results:
            src = res.proxy.source
            if not src:
                continue

            if src in source_stats:
                stats = source_stats[src]
                stats["alive"] += 1
                stats["scores"].append(res.score)
                stats["speeds"].append(res.speed)

        # Calculate and record
        for source, total in source_totals.items():
            stats = source_stats[source]
            alive = stats["alive"]
            dead = total - alive

            avg_score = sum(stats["scores"]) / alive if alive > 0 else 0.0
            avg_speed = sum(stats["speeds"]) / alive if alive > 0 else 0.0

            self.health_tracker.record_check(
                source,
                scraped=0,  # Already recorded during scrape
                alive=alive,
                dead=dead,
                avg_score=avg_score,
                avg_speed=avg_speed,
            )
