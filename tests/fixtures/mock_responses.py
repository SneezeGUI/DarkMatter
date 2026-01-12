"""
Mock response builders for testing validators and proxy systems.

Provides factory functions to create realistic mock responses from various
IP validation services, proxy check results, and traffic configurations.
"""

from typing import Any

from core.models import (
    BrowserConfig,
    BrowserSelection,
    CaptchaConfig,
    CaptchaProvider,
    EngineMode,
    ProtectionBypassConfig,
    ProxyCheckResult,
    ProxyConfig,
    TrafficConfig,
)

# =============================================================================
# Validator Response Builders
# =============================================================================


def build_httpbin_response(
    origin: str = "1.2.3.4",
    headers: dict[str, str] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Build a mock httpbin.org/get response.

    Args:
        origin: The origin IP (or comma-separated IPs)
        headers: Override default headers completely
        extra_headers: Add headers to default set (for leak testing)

    Returns:
        Dict matching httpbin.org response format
    """
    default_headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
        "Host": "httpbin.org",
        "User-Agent": "curl/7.68.0",
    }

    if headers is not None:
        final_headers = headers
    else:
        final_headers = default_headers.copy()
        if extra_headers:
            final_headers.update(extra_headers)

    return {
        "args": {},
        "headers": final_headers,
        "origin": origin,
        "url": "https://httpbin.org/get",
    }


def build_ipapi_response(
    ip: str = "1.2.3.4",
    country: str = "United States",
    city: str = "New York",
    proxy: bool = False,
    hosting: bool = False,
    status: str = "success",
    message: str = "",
) -> dict[str, Any]:
    """
    Build a mock ip-api.com/json response.

    Args:
        ip: The detected query IP
        country: Country name
        city: City name
        proxy: Whether flagged as proxy
        hosting: Whether flagged as datacenter/hosting
        status: "success" or "fail"
        message: Error message if status is "fail"

    Returns:
        Dict matching ip-api.com response format
    """
    response = {
        "status": status,
        "query": ip,
        "country": country,
        "city": city,
        "proxy": proxy,
        "hosting": hosting,
    }
    if message:
        response["message"] = message
    return response


def build_ipify_response(ip: str = "1.2.3.4") -> dict[str, str]:
    """
    Build a mock api.ipify.org response.

    Args:
        ip: The detected IP

    Returns:
        Dict matching ipify.org response format
    """
    return {"ip": ip}


def build_ipinfo_response(
    ip: str = "1.2.3.4",
    hostname: str = "example.com",
    city: str = "New York",
    region: str = "New York",
    country: str = "US",
    org: str = "AS12345 Example ISP",
    privacy: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """
    Build a mock ipinfo.io/json response.

    Args:
        ip: The detected IP
        hostname: PTR record hostname
        city: City name
        region: Region/state name
        country: 2-letter country code
        org: AS number and organization
        privacy: Privacy detection flags (proxy, vpn, hosting)

    Returns:
        Dict matching ipinfo.io response format
    """
    response = {
        "ip": ip,
        "hostname": hostname,
        "city": city,
        "region": region,
        "country": country,
        "org": org,
        "loc": "40.7128,-74.0060",
        "postal": "10001",
        "timezone": "America/New_York",
    }
    if privacy is not None:
        response["privacy"] = privacy
    return response


def build_wtfismyip_response(
    ip: str = "1.2.3.4",
    hostname: str = "example.com",
    location: str = "New York, US",
) -> dict[str, str]:
    """
    Build a mock wtfismyip.com/json response.

    Args:
        ip: The detected IP
        hostname: Reverse DNS hostname
        location: Geographic location string

    Returns:
        Dict matching wtfismyip.com response format
    """
    return {
        "YourFuckingIPAddress": ip,
        "YourFuckingHostname": hostname,
        "YourFuckingLocation": location,
        "YourFuckingISP": "Example ISP",
        "YourFuckingTorExit": "false",
        "YourFuckingCountryCode": "US",
    }


def build_azenv_response(
    ip: str = "1.2.3.4",
    extra_env_vars: dict[str, str] | None = None,
) -> str:
    """
    Build a mock azenv.net HTML response.

    Args:
        ip: The REMOTE_ADDR IP
        extra_env_vars: Additional environment variables (for header leak testing)

    Returns:
        String matching azenv.net HTML format
    """
    lines = [
        f"REMOTE_ADDR = {ip}",
        "REMOTE_HOST = unknown",
        "HTTP_HOST = azenv.net",
        "HTTP_USER_AGENT = curl/7.68.0",
        "HTTP_ACCEPT = */*",
        "SERVER_SOFTWARE = Apache/2.4",
        "SERVER_NAME = azenv.net",
        "REQUEST_METHOD = GET",
        "QUERY_STRING = ",
    ]

    if extra_env_vars:
        for key, value in extra_env_vars.items():
            lines.append(f"{key} = {value}")

    return "\n".join(lines)


# =============================================================================
# Model Factory Functions
# =============================================================================


def build_proxy_config(
    host: str = "192.168.1.1",
    port: int = 8080,
    protocol: str = "http",
    username: str = "",
    password: str = "",
    source: str = "",
) -> ProxyConfig:
    """
    Build a ProxyConfig instance for testing.

    Args:
        host: Proxy host IP or hostname
        port: Proxy port
        protocol: "http", "socks4", or "socks5"
        username: Auth username (optional)
        password: Auth password (optional)
        source: Source URL (optional)

    Returns:
        ProxyConfig instance
    """
    return ProxyConfig(
        host=host,
        port=port,
        protocol=protocol,
        username=username,
        password=password,
        source=source,
    )


def build_proxy_check_result(
    host: str = "192.168.1.1",
    port: int = 8080,
    protocol: str = "http",
    status: str = "Active",
    speed: int = 150,
    country: str = "United States",
    country_code: str = "US",
    city: str = "New York",
    anonymity: str = "Elite",
    bytes_transferred: int = 1024,
) -> ProxyCheckResult:
    """
    Build a ProxyCheckResult instance for testing.

    Args:
        host: Proxy host IP
        port: Proxy port
        protocol: Protocol type (HTTP, SOCKS4, SOCKS5)
        status: "Active", "Dead", or "Error"
        speed: Response time in milliseconds
        country: Full country name
        country_code: 2-letter country code
        city: City name
        anonymity: "Elite", "Anonymous", "Transparent", "Unknown"
        bytes_transferred: Bytes transferred during check

    Returns:
        ProxyCheckResult instance
    """
    proxy = build_proxy_config(host=host, port=port, protocol=protocol.lower())
    return ProxyCheckResult(
        proxy=proxy,
        status=status,
        speed=speed,
        type=protocol.upper(),
        country=country,
        country_code=country_code,
        city=city,
        anonymity=anonymity,
        bytes_transferred=bytes_transferred,
    )


def build_traffic_config(
    target_url: str = "https://example.com",
    max_threads: int = 5,
    total_visits: int = 0,
    min_duration: int = 5,
    max_duration: int = 10,
    headless: bool = True,
    verify_ssl: bool = True,
    engine_mode: EngineMode = EngineMode.CURL,
    burst_mode: bool = False,
    burst_requests: int = 10,
    burst_sleep_min: float = 1.0,
    burst_sleep_max: float = 3.0,
    **browser_overrides: Any,
) -> TrafficConfig:
    """
    Build a TrafficConfig instance with sensible test defaults.

    Args:
        target_url: Target URL for traffic
        max_threads: Maximum concurrent threads
        total_visits: Total visits (0 = infinite)
        min_duration: Minimum view time in seconds
        max_duration: Maximum view time in seconds
        headless: Run browser in headless mode
        verify_ssl: Verify SSL certificates
        engine_mode: CURL or BROWSER
        burst_mode: Enable burst mode
        burst_requests: Requests per burst
        burst_sleep_min: Minimum sleep between bursts
        burst_sleep_max: Maximum sleep between bursts
        **browser_overrides: Override BrowserConfig fields

    Returns:
        TrafficConfig instance
    """
    browser_defaults = {
        "selected_browser": BrowserSelection.AUTO,
        "chrome_path": "",
        "chromium_path": "",
        "edge_path": "",
        "brave_path": "",
        "firefox_path": "",
        "other_path": "",
        "headless": headless,
        "max_contexts": 3,
        "locale": "en-US",
        "timezone": "America/New_York",
        "stealth_enabled": True,
    }
    browser_defaults.update(browser_overrides)

    return TrafficConfig(
        target_url=target_url,
        max_threads=max_threads,
        total_visits=total_visits,
        min_duration=min_duration,
        max_duration=max_duration,
        headless=headless,
        verify_ssl=verify_ssl,
        engine_mode=engine_mode,
        browser=BrowserConfig(**browser_defaults),
        captcha=CaptchaConfig(
            twocaptcha_key="",
            anticaptcha_key="",
            primary_provider=CaptchaProvider.NONE,
            fallback_enabled=False,
            timeout_seconds=120,
        ),
        protection=ProtectionBypassConfig(
            cloudflare_enabled=False,
            cloudflare_wait_seconds=10,
            akamai_enabled=False,
            auto_solve_captcha=False,
        ),
        burst_mode=burst_mode,
        burst_requests=burst_requests,
        burst_sleep_min=burst_sleep_min,
        burst_sleep_max=burst_sleep_max,
    )


# =============================================================================
# HTTP Response Builders (for mocking requests/aiohttp)
# =============================================================================


def build_http_response(
    status_code: int = 200,
    body: str | dict = "",
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Build a generic HTTP response dict for mocking.

    Args:
        status_code: HTTP status code
        body: Response body (string or dict for JSON)
        headers: Response headers

    Returns:
        Dict with status_code, body, and headers
    """
    return {
        "status_code": status_code,
        "body": body,
        "headers": headers or {"Content-Type": "application/json"},
    }


def build_proxy_list(
    count: int = 10,
    protocols: list[str] | None = None,
    base_ip: str = "192.168.1.",
    base_port: int = 8080,
) -> list[ProxyConfig]:
    """
    Build a list of ProxyConfig instances for testing.

    Args:
        count: Number of proxies to generate
        protocols: List of protocols to cycle through
        base_ip: Base IP prefix (last octet will be incremented)
        base_port: Starting port number

    Returns:
        List of ProxyConfig instances
    """
    if protocols is None:
        protocols = ["http", "socks4", "socks5"]

    proxies = []
    for i in range(count):
        proxies.append(
            build_proxy_config(
                host=f"{base_ip}{(i % 254) + 1}",
                port=base_port + (i % 100),
                protocol=protocols[i % len(protocols)],
            )
        )
    return proxies
