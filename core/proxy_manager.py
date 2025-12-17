import re
import time
import logging
import os
import requests as std_requests
from typing import List, Callable, Optional, Set, Dict
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests
from .header_manager import HeaderManager
from .models import ProxyConfig, ProxyCheckResult
from .constants import (
    SCRAPE_TIMEOUT_SECONDS,
    PROXY_CHECK_BATCH_SIZE,
    DEAD_PROXY_SPEED_MS,
)
from .validators import (
    DEFAULT_VALIDATORS, Validator, ValidatorResult,
    aggregate_results, AggregatedResult
)

# GeoIP cache to avoid repeated lookups
_geoip_cache: Dict[str, dict] = {}

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
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "GeoLite2-City.mmdb"),
        os.path.join(os.path.dirname(__file__), "..", "resources", "GeoLite2-City.mmdb"),
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
        logging.warning("geoip2 package not installed, will use API fallback. Run: pip install geoip2")
        return None
    except Exception as e:
        logging.warning(f"Failed to load GeoLite2 database: {e}")
        return None


def _lookup_geoip_local(ip: str) -> Optional[dict]:
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
            "city": response.city.name or ""
        }
    except Exception:
        # IP not found in database or other error
        return None


def _lookup_geoip_api(ip: str) -> dict:
    """
    Look up geographic information using multiple API fallbacks.
    Tries multiple providers in sequence until one succeeds.
    Returns dict with country, countryCode, city.
    """
    default = {"country": "Unknown", "countryCode": "??", "city": ""}

    # API 1: ip-api.com (free, 45 req/min)
    try:
        resp = std_requests.get(
            f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,city",
            timeout=3
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                return {
                    "country": data.get("country", "Unknown"),
                    "countryCode": data.get("countryCode", "??"),
                    "city": data.get("city", "")
                }
    except Exception as e:
        logging.debug(f"GeoIP ip-api.com failed for {ip}: {e}")

    # API 2: ipapi.co (free, 1000 req/day)
    try:
        resp = std_requests.get(
            f"https://ipapi.co/{ip}/json/",
            timeout=3,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if resp.status_code == 200:
            data = resp.json()
            if not data.get("error"):
                return {
                    "country": data.get("country_name", "Unknown"),
                    "countryCode": data.get("country_code", "??"),
                    "city": data.get("city", "")
                }
    except Exception as e:
        logging.debug(f"GeoIP ipapi.co failed for {ip}: {e}")

    # API 3: ipwhois.io (free, 10000 req/month)
    try:
        resp = std_requests.get(
            f"https://ipwhois.app/json/{ip}",
            timeout=3
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success", True):  # ipwhois returns success=false on error
                return {
                    "country": data.get("country", "Unknown"),
                    "countryCode": data.get("country_code", "??"),
                    "city": data.get("city", "")
                }
    except Exception as e:
        logging.debug(f"GeoIP ipwhois.app failed for {ip}: {e}")

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

    # Fall back to API if local lookup failed
    if result is None:
        result = _lookup_geoip_api(ip)

    _geoip_cache[ip] = result
    return result


def detect_anonymity(response_data: dict, real_ip: str, proxy_ip: str) -> str:
    """
    Detect proxy anonymity level based on response headers and origin.

    Levels:
    - Elite (L1): No proxy detection, real IP completely hidden
    - Anonymous (L2): Proxy detected but real IP hidden
    - Transparent (L3): Real IP is exposed
    - Unknown: Cannot determine (response missing required fields)

    Args:
        response_data: JSON response from httpbin-like service (e.g., /get, /ip)
        real_ip: The user's real IP address
        proxy_ip: The proxy's IP address

    Returns:
        Anonymity level string

    Note:
        For accurate detection, use test URLs that return origin/headers like:
        - https://httpbin.org/get
        - https://httpbin.org/ip
        NOT https://httpbin.org/json (doesn't return needed fields)
    """
    # Check if response has the fields we need for detection
    origin = response_data.get("origin", "")
    headers = response_data.get("headers", {})

    # If response doesn't have origin OR headers, we can't reliably detect
    # This happens with endpoints like /json that don't return this data
    has_detection_data = bool(origin) or bool(headers)

    if not has_detection_data:
        return "Unknown"

    # If real IP appears in origin, it's transparent
    if real_ip and origin and real_ip in origin:
        return "Transparent"

    # Headers that expose real IP (Transparent)
    ip_exposing_headers = [
        "X-Forwarded-For",
        "X-Real-Ip",
        "X-Client-Ip",
        "Client-Ip",
        "Forwarded",
        "Cf-Connecting-Ip",
        "True-Client-Ip"
    ]

    for header in ip_exposing_headers:
        value = headers.get(header, "")
        if value:
            # Check if real IP is exposed
            if real_ip and real_ip in value:
                return "Transparent"
            # Header exists with some value but not our IP - Anonymous
            # (proxy is adding forwarding headers but hiding real IP)

    # Headers that indicate proxy usage (Anonymous)
    proxy_revealing_headers = [
        "Via",
        "X-Forwarded-For",
        "X-Proxy-Id",
        "Proxy-Connection",
        "X-Bluecoat-Via",
        "Proxy-Authenticate",
        "Proxy-Authorization"
    ]

    for header in proxy_revealing_headers:
        if headers.get(header):
            return "Anonymous"

    # Has detection data but no proxy indicators found - Elite
    if has_detection_data:
        return "Elite"

    return "Unknown"


class ThreadedProxyManager:
    def __init__(self):
        self.regex_pattern = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b")

    def scrape(self, sources: List[str], protocols: List[str], max_threads: int = 20, scraper_proxy: str = None, on_progress: Callable[[int], None] = None) -> List[ProxyConfig]:
        """Scrapes proxies from provided source URLs using threads."""
        found_proxies: Set[tuple] = set()
        
        def fetch_source(url: str):
            try:
                # Use standard requests for speed (scraping text/html usually doesn't need TLS fingerprinting)
                # But we use rotating headers to avoid 403s
                h = HeaderManager.get_random_headers()
                proxies = {"http": scraper_proxy, "https": scraper_proxy} if scraper_proxy else None
                
                response = std_requests.get(
                    url,
                    timeout=SCRAPE_TIMEOUT_SECONDS,
                    headers=h,
                    proxies=proxies
                )
                if response.status_code == 200:
                    if on_progress:
                        on_progress(len(response.content))
                    matches = self.regex_pattern.findall(response.text)
                    
                    # Smart Protocol Detection
                    u_lower = url.lower()
                    source_protos = []
                    
                    # Heuristics based on URL hints
                    if "socks5" in u_lower: source_protos.append("socks5")
                    if "socks4" in u_lower: source_protos.append("socks4")
                    if "http" in u_lower and "socks" not in u_lower: source_protos.append("http")
                    
                    # Intersect with user requests
                    valid_protos = [p for p in source_protos if p in protocols]
                    
                    # Fallback: If no specific protocol detected, try all requested
                    if not valid_protos:
                        valid_protos = protocols

                    for m in matches:
                        ip, port = m.split(":")
                        for proto in valid_protos:
                            found_proxies.add((ip, int(port), proto))
            except Exception as e:
                logging.debug(f"Error scraping {url}: {e}")

        with ThreadPoolExecutor(max_workers=max_threads) as ex:
             ex.map(fetch_source, [url for url in sources if url.strip() and not url.startswith("#")])

        results = []
        for ip, port, proto in found_proxies:
            results.append(ProxyConfig(host=ip, port=port, protocol=proto))
                
        return results

    def check_proxies(self, proxies: List[ProxyConfig], target_url: str, timeout_ms: int, real_ip: str,
                          on_progress: Callable[[ProxyCheckResult, int, int], None], concurrency: int = 100,
                          pause_checker: Optional[Callable[[], bool]] = None,
                          validators: Optional[List[Validator]] = None,
                          test_depth: str = "quick") -> List[ProxyCheckResult]:
        """
        Checks a list of proxies concurrently using threads.
        """
        total = len(proxies)
        completed = 0
        valid_results = []
        lock = logging.threading.Lock() # Simple lock for counter

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

            result = self._test_proxy(proxy, target_url, timeout_ms, real_ip, active_validators)

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
            batch_sleep = 0.05 if concurrency <= 500 else 0.02 if concurrency <= 2000 else 0.01

            # Staggered Launch to prevent UI freeze
            for i in range(0, len(proxies), batch_size):
                batch = proxies[i:i + batch_size]
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

        return valid_results_list

    def _test_proxy(self, proxy: ProxyConfig, target_url: str, timeout_ms: int, real_ip: str,
                    validators: Optional[List[Validator]] = None) -> ProxyCheckResult:
        result = ProxyCheckResult(
            proxy=proxy,
            status="Dead",
            speed=DEAD_PROXY_SPEED_MS,
            type=proxy.protocol.upper(),
            country="Unknown",
            country_code="??",
            city=""
        )

        proxy_url = proxy.to_curl_cffi_format()
        proxies_dict = {"http": proxy_url, "https": proxy_url}
        timeout_sec = max(timeout_ms / 1000, 1.0)  # Minimum 1 second timeout

        # Track bytes transferred for bandwidth calculation
        bytes_transferred = 0
        is_https = target_url.lower().startswith("https://")

        start_time = time.time()
        try:
            # Synchronous Session - don't pass proxies to constructor, pass to request
            with requests.Session(impersonate="chrome120") as session:
                resp = session.get(
                    target_url,
                    timeout=timeout_sec,
                    proxies=proxies_dict,
                    verify=False  # Many proxy test endpoints have cert issues
                )

                latency = int((time.time() - start_time) * 1000)
                result.speed = latency
                result.status = "Active"

                # Calculate bytes transferred:
                # - Request: ~500 bytes (method + URL + headers)
                # - Response headers: ~300 bytes typical
                # - Response body: actual content length
                # - TLS handshake: ~5KB for HTTPS (client hello, server hello, certs, key exchange)
                # - Proxy CONNECT overhead: ~200 bytes for HTTPS through proxy
                request_overhead = 500
                response_headers = 300
                response_body = len(resp.content) if resp.content else 0
                tls_overhead = 5000 if is_https else 0
                proxy_connect = 200 if is_https else 0

                bytes_transferred = request_overhead + response_headers + response_body + tls_overhead + proxy_connect

                # If target was HTTPS and it worked, label as HTTPS proxy
                if is_https and result.type == "HTTP":
                    result.type = "HTTPS"

                # HTTPS tunneling test for HTTP proxies that weren't tested with HTTPS
                # This is critical because browser mode requires HTTPS tunneling
                if not is_https and result.type == "HTTP":
                    https_capable = self._test_https_tunnel(session, proxies_dict, timeout_sec)
                    if https_capable:
                        result.type = "HTTPS"
                        bytes_transferred += 2000  # HTTPS test overhead
                        logging.debug(f"Proxy {proxy.host}:{proxy.port} upgraded to HTTPS (tunnel test passed)")
                    else:
                        # Mark as HTTP-only - won't work for HTTPS sites in browser mode
                        logging.debug(f"Proxy {proxy.host}:{proxy.port} is HTTP-only (HTTPS tunnel failed)")

                # Get proxy's exit IP for GeoIP lookup
                proxy_exit_ip = None
                response_data = {}

                try:
                    response_data = resp.json()
                    # Extract origin IP from httpbin-like response
                    origin = response_data.get("origin", "")
                    if origin:
                        # Origin might be "ip1, ip2" format - take first
                        proxy_exit_ip = origin.split(",")[0].strip()
                except (ValueError, KeyError, AttributeError):
                    pass

                # GeoIP lookup for country/city
                if proxy_exit_ip:
                    geo = lookup_geoip(proxy_exit_ip)
                    result.country = geo.get("country", "Unknown")
                    result.country_code = geo.get("countryCode", "??")
                    result.city = geo.get("city", "")

                # Multi-validator anonymity detection
                if validators and len(validators) > 0:
                    # Run multi-validator test
                    validator_results, validator_bytes = self._run_validators(
                        session, proxy, proxies_dict, validators, timeout_sec, real_ip
                    )
                    bytes_transferred += validator_bytes
                    # Pass proxy_exit_ip and proxy_worked for better fallback handling
                    aggregated = aggregate_results(
                        validator_results, real_ip,
                        proxy_exit_ip=proxy_exit_ip or "",
                        proxy_worked=True  # We're in the success path
                    )
                    result.anonymity = aggregated.anonymity_level
                    # Store score from aggregation (0-100)
                    anon_score_factor = max(0.5, aggregated.anonymity_score / 100.0)
                elif response_data:
                    # Fallback to simple detection
                    result.anonymity = detect_anonymity(response_data, real_ip, proxy_exit_ip or proxy.host)
                    anon_score_factor = {"Elite": 1.5, "Anonymous": 1.0, "Transparent": 0.5}.get(result.anonymity, 0.8)
                else:
                    # No validators and no response data - use IP comparison fallback
                    if proxy_exit_ip and real_ip:
                        if proxy_exit_ip == real_ip:
                            result.anonymity = "Transparent"
                            anon_score_factor = 0.5
                        else:
                            # Different IP = at least Anonymous
                            result.anonymity = "Anonymous"
                            anon_score_factor = 1.0
                    else:
                        # Proxy worked but no IP data - assume Anonymous as safe default
                        result.anonymity = "Anonymous"
                        anon_score_factor = 0.8

                # Store bytes transferred
                result.bytes_transferred = bytes_transferred

                # Score Calculation
                # Higher is better. 1000ms = 1.0. 100ms = 10.0.
                base_score = 1000.0 / max(latency, 1)
                base_score *= anon_score_factor

                result.score = round(base_score, 2)
                proxy.score = result.score  # Store on config for Engine use

        except Exception as e:
            # Log failed proxies at debug level for troubleshooting
            logging.debug(f"Proxy {proxy.host}:{proxy.port} failed: {type(e).__name__}: {e}")
            # Even failed attempts use some bandwidth (connection attempt + TLS hello)
            result.bytes_transferred = 1500 if is_https else 500

        return result

    def _run_validators(self, session, proxy: ProxyConfig, proxies_dict: dict,
                        validators: List[Validator], timeout_sec: float,
                        real_ip: str) -> tuple:
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
                    verify=False
                )
                elapsed_ms = int((time.time() - start) * 1000)

                # Calculate bytes for this validator request
                request_overhead = 500
                response_headers = 300
                response_body = len(resp.content) if resp.content else 0
                # TLS overhead only for first HTTPS request in session (session reuse)
                # Subsequent HTTPS requests reuse connection, so minimal TLS overhead
                tls_overhead = 500 if is_https else 0  # Session reuse = smaller overhead
                total_bytes += request_overhead + response_headers + response_body + tls_overhead

                vr = validator.parse_response(resp.text, resp.status_code, real_ip)
                vr.response_time_ms = elapsed_ms
                results.append(vr)

            except Exception as e:
                # Validator failed - record failure
                results.append(ValidatorResult(
                    validator_name=validator.name,
                    success=False,
                    error=str(e)
                ))
                # Failed request still used some bandwidth
                total_bytes += 800 if is_https else 300

        return results, total_bytes

    def _test_https_tunnel(self, session, proxies_dict: dict, timeout_sec: float) -> bool:
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
                    verify=False
                )
                if resp.status_code == 200:
                    return True
            except Exception:
                # Try next URL
                continue

        return False
