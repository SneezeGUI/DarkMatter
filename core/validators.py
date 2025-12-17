"""
Proxy Validator System - Multi-endpoint anonymity testing.

Supports multiple validator endpoints to comprehensively test proxy anonymity,
IP detection, and header leakage.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable
from enum import Enum


class ValidatorType(Enum):
    """Type of test the validator performs."""
    HEADERS = "headers"         # Returns request headers
    IP_INFO = "ip_info"         # Returns IP and geolocation
    PROXY_DETECT = "proxy_detect"  # Specifically detects proxy usage
    COMPREHENSIVE = "comprehensive"  # Full leak test


@dataclass
class ValidatorResult:
    """Result from a single validator test."""
    validator_name: str
    success: bool
    response_time_ms: int = 0
    # IP Detection
    detected_ip: str = ""
    real_ip_exposed: bool = False
    # Header Analysis
    proxy_headers_found: List[str] = field(default_factory=list)
    forwarded_ips: List[str] = field(default_factory=list)
    # Proxy Detection
    flagged_as_proxy: bool = False
    flagged_as_vpn: bool = False
    flagged_as_datacenter: bool = False
    # Raw data for debugging
    raw_response: Dict = field(default_factory=dict)
    error: str = ""


@dataclass
class AggregatedResult:
    """Aggregated result from all validators."""
    anonymity_level: str = "Unknown"  # Elite, Anonymous, Transparent
    anonymity_score: int = 0  # 0-100 score
    validators_passed: int = 0
    validators_failed: int = 0
    validators_total: int = 0
    # Detailed findings
    real_ip_exposed: bool = False
    proxy_detected: bool = False
    datacenter_detected: bool = False
    leaking_headers: List[str] = field(default_factory=list)
    # Per-validator results
    results: List[ValidatorResult] = field(default_factory=list)


# Headers that expose the real IP (Transparent proxy indicators)
IP_EXPOSING_HEADERS = [
    "X-Forwarded-For",
    "X-Real-Ip",
    "X-Real-IP",
    "X-Client-Ip",
    "X-Client-IP",
    "Client-Ip",
    "Client-IP",
    "Forwarded",
    "Forwarded-For",
    "X-Originating-Ip",
    "X-Originating-IP",
    "Cf-Connecting-Ip",
    "CF-Connecting-IP",
    "True-Client-Ip",
    "True-Client-IP",
    "X-Cluster-Client-Ip",
    "X-Cluster-Client-IP",
    "Fastly-Client-Ip",
    "X-Forwarded",
    "Forwarded-For-Ip",
]

# Headers that reveal proxy usage (Anonymous proxy indicators)
PROXY_REVEALING_HEADERS = [
    "Via",
    "X-Proxy-Id",
    "X-Proxy-ID",
    "Proxy-Connection",
    "X-Bluecoat-Via",
    "X-Cache",
    "X-Cached",
    "X-Varnish",
    "X-Squid",
    "Surrogate-Control",
    "Proxy-Authenticate",
    "X-Proxy-Connection",
    "Proxy-Agent",
    "X-Forwarded-Proto",
    "X-Forwarded-Host",
    "X-Forwarded-Server",
    "X-ProxyUser-Ip",
]


class Validator:
    """Base validator with parsing logic for different response formats."""

    def __init__(
        self,
        name: str,
        url: str,
        validator_type: ValidatorType,
        response_format: str = "json",  # json, html, text
        enabled: bool = True,
        timeout: int = 10,
        description: str = "",
    ):
        self.name = name
        self.url = url
        self.validator_type = validator_type
        self.response_format = response_format
        self.enabled = enabled
        self.timeout = timeout
        self.description = description

    def parse_response(self, response_text: str, status_code: int, real_ip: str) -> ValidatorResult:
        """Parse response and return ValidatorResult. Override in subclasses."""
        result = ValidatorResult(validator_name=self.name, success=status_code == 200)
        if not result.success:
            result.error = f"HTTP {status_code}"
            return result

        try:
            if self.response_format == "json":
                import json
                data = json.loads(response_text)
                result.raw_response = data
                self._parse_json(data, real_ip, result)
            elif self.response_format == "html":
                self._parse_html(response_text, real_ip, result)
            else:
                self._parse_text(response_text, real_ip, result)
        except Exception as e:
            result.error = str(e)
            result.success = False

        return result

    def _parse_json(self, data: dict, real_ip: str, result: ValidatorResult):
        """Override in subclasses for specific JSON parsing."""
        pass

    def _parse_html(self, html: str, real_ip: str, result: ValidatorResult):
        """Override in subclasses for specific HTML parsing."""
        pass

    def _parse_text(self, text: str, real_ip: str, result: ValidatorResult):
        """Override in subclasses for specific text parsing."""
        pass

    def to_dict(self) -> dict:
        """Convert to dictionary for settings storage."""
        return {
            "name": self.name,
            "url": self.url,
            "type": self.validator_type.value,
            "enabled": self.enabled,
            "timeout": self.timeout,
            "description": self.description,
        }


class HttpBinValidator(Validator):
    """httpbin.org - Returns headers and origin IP."""

    def __init__(self):
        super().__init__(
            name="httpbin.org",
            url="https://httpbin.org/get",
            validator_type=ValidatorType.HEADERS,
            response_format="json",
            description="Header analysis & origin IP"
        )

    def _parse_json(self, data: dict, real_ip: str, result: ValidatorResult):
        # Extract origin IP
        origin = data.get("origin", "")
        if origin:
            # Origin can be "ip1, ip2" format
            result.detected_ip = origin.split(",")[0].strip()

        # Check headers
        headers = data.get("headers", {})

        # Check for IP-exposing headers
        for header in IP_EXPOSING_HEADERS:
            value = headers.get(header, "") or headers.get(header.lower(), "")
            if value:
                result.proxy_headers_found.append(header)
                # Check if real IP is in the value
                if real_ip and real_ip in value:
                    result.real_ip_exposed = True
                    result.forwarded_ips.append(f"{header}: {value}")

        # Check for proxy-revealing headers
        for header in PROXY_REVEALING_HEADERS:
            value = headers.get(header, "") or headers.get(header.lower(), "")
            if value:
                if header not in result.proxy_headers_found:
                    result.proxy_headers_found.append(header)


class IpApiValidator(Validator):
    """ip-api.com - IP geolocation with proxy/VPN detection."""

    def __init__(self):
        super().__init__(
            name="ip-api.com",
            url="http://ip-api.com/json/?fields=status,message,query,proxy,hosting",
            validator_type=ValidatorType.PROXY_DETECT,
            response_format="json",
            description="Proxy/VPN/Datacenter detection"
        )

    def _parse_json(self, data: dict, real_ip: str, result: ValidatorResult):
        if data.get("status") != "success":
            result.error = data.get("message", "API error")
            result.success = False
            return

        result.detected_ip = data.get("query", "")

        # Check if flagged as proxy
        if data.get("proxy", False):
            result.flagged_as_proxy = True

        # Check if datacenter/hosting IP
        if data.get("hosting", False):
            result.flagged_as_datacenter = True

        # Check if real IP exposed
        if real_ip and result.detected_ip == real_ip:
            result.real_ip_exposed = True


class IpifyValidator(Validator):
    """ipify.org - Simple IP detection."""

    def __init__(self):
        super().__init__(
            name="ipify.org",
            url="https://api.ipify.org?format=json",
            validator_type=ValidatorType.IP_INFO,
            response_format="json",
            description="Simple IP detection"
        )

    def _parse_json(self, data: dict, real_ip: str, result: ValidatorResult):
        result.detected_ip = data.get("ip", "")
        if real_ip and result.detected_ip == real_ip:
            result.real_ip_exposed = True


class IpInfoValidator(Validator):
    """ipinfo.io - IP info with privacy detection."""

    def __init__(self):
        super().__init__(
            name="ipinfo.io",
            url="https://ipinfo.io/json",
            validator_type=ValidatorType.PROXY_DETECT,
            response_format="json",
            description="IP info with privacy flags"
        )

    def _parse_json(self, data: dict, real_ip: str, result: ValidatorResult):
        result.detected_ip = data.get("ip", "")

        # ipinfo.io privacy field (requires token for full access)
        privacy = data.get("privacy", {})
        if privacy:
            if privacy.get("proxy", False):
                result.flagged_as_proxy = True
            if privacy.get("vpn", False):
                result.flagged_as_vpn = True
            if privacy.get("hosting", False):
                result.flagged_as_datacenter = True

        if real_ip and result.detected_ip == real_ip:
            result.real_ip_exposed = True


class AzenvValidator(Validator):
    """azenv.net - Shows all HTTP headers (legacy but comprehensive)."""

    def __init__(self):
        super().__init__(
            name="azenv.net",
            url="http://azenv.net/",
            validator_type=ValidatorType.HEADERS,
            response_format="html",
            description="Full header dump"
        )

    def _parse_html(self, html: str, real_ip: str, result: ValidatorResult):
        # azenv.net returns headers in format: HEADER_NAME = value
        lines = html.split("\n")

        for line in lines:
            line = line.strip()
            if "=" in line:
                # Parse REMOTE_ADDR for IP
                if line.startswith("REMOTE_ADDR"):
                    ip = line.split("=", 1)[1].strip()
                    result.detected_ip = ip
                    if real_ip and real_ip == ip:
                        result.real_ip_exposed = True

                # Check for forwarded headers (HTTP_X_FORWARDED_FOR format)
                for header in IP_EXPOSING_HEADERS:
                    env_name = "HTTP_" + header.upper().replace("-", "_")
                    if line.startswith(env_name):
                        value = line.split("=", 1)[1].strip()
                        result.proxy_headers_found.append(header)
                        if real_ip and real_ip in value:
                            result.real_ip_exposed = True
                            result.forwarded_ips.append(f"{header}: {value}")

                # Check proxy-revealing headers
                for header in PROXY_REVEALING_HEADERS:
                    env_name = "HTTP_" + header.upper().replace("-", "_")
                    if line.startswith(env_name):
                        if header not in result.proxy_headers_found:
                            result.proxy_headers_found.append(header)


class WhatIsMyIpValidator(Validator):
    """wtfismyip.com - IP with proxy detection hints."""

    def __init__(self):
        super().__init__(
            name="wtfismyip.com",
            url="https://wtfismyip.com/json",
            validator_type=ValidatorType.IP_INFO,
            response_format="json",
            description="IP detection"
        )

    def _parse_json(self, data: dict, real_ip: str, result: ValidatorResult):
        result.detected_ip = data.get("YourFuckingIPAddress", "")
        if real_ip and result.detected_ip == real_ip:
            result.real_ip_exposed = True


# Default validators list - ordered by reliability
DEFAULT_VALIDATORS: List[Validator] = [
    HttpBinValidator(),
    IpApiValidator(),
    IpifyValidator(),
    IpInfoValidator(),
    AzenvValidator(),
    WhatIsMyIpValidator(),
]


def get_validator_by_name(name: str) -> Optional[Validator]:
    """Get a validator instance by name."""
    for v in DEFAULT_VALIDATORS:
        if v.name == name:
            return v
    return None


def aggregate_results(results: List[ValidatorResult], real_ip: str,
                      proxy_exit_ip: str = "", proxy_worked: bool = True) -> AggregatedResult:
    """
    Aggregate results from multiple validators into a final anonymity assessment.

    Scoring:
    - Start at 100 (Elite)
    - -50 if real IP exposed anywhere
    - -20 if flagged as proxy by any detector
    - -10 if datacenter IP detected
    - -5 per proxy-revealing header found
    - Minimum score: 0

    Levels:
    - 80-100: Elite (L1)
    - 50-79: Anonymous (L2)
    - 1-49: Transparent (L3)
    - 0: Transparent (definitely exposed)

    Args:
        results: List of ValidatorResult from each validator
        real_ip: User's real IP address
        proxy_exit_ip: The proxy's detected exit IP (from initial request)
        proxy_worked: Whether the proxy successfully connected (Active status)
    """
    agg = AggregatedResult()
    agg.results = results
    agg.validators_total = len(results)

    score = 100
    all_headers = set()
    detected_ips = set()  # Collect all detected IPs for cross-validation

    for r in results:
        if r.success:
            agg.validators_passed += 1
            if r.detected_ip:
                detected_ips.add(r.detected_ip)
        else:
            agg.validators_failed += 1
            continue

        # Check for real IP exposure
        if r.real_ip_exposed:
            agg.real_ip_exposed = True
            score -= 50

        # Check proxy detection flags
        if r.flagged_as_proxy or r.flagged_as_vpn:
            agg.proxy_detected = True
            score -= 20

        if r.flagged_as_datacenter:
            agg.datacenter_detected = True
            score -= 10

        # Collect all leaking headers
        for h in r.proxy_headers_found:
            all_headers.add(h)

    # Deduct for each unique proxy header found
    score -= len(all_headers) * 5

    # Clamp score
    agg.anonymity_score = max(0, min(100, score))
    agg.leaking_headers = list(all_headers)

    # Determine level
    if agg.real_ip_exposed:
        agg.anonymity_level = "Transparent"
    elif agg.anonymity_score >= 80:
        agg.anonymity_level = "Elite"
    elif agg.anonymity_score >= 50:
        agg.anonymity_level = "Anonymous"
    else:
        agg.anonymity_level = "Transparent"

    # Handle no successful validators - use fallback logic
    if agg.validators_passed == 0:
        # Fallback: If proxy worked and we have exit IP info, infer anonymity
        if proxy_worked and proxy_exit_ip and real_ip:
            if proxy_exit_ip == real_ip:
                # Proxy is transparent - our real IP is showing
                agg.anonymity_level = "Transparent"
                agg.anonymity_score = 0
                agg.real_ip_exposed = True
            else:
                # Proxy is at least hiding our IP - assume Anonymous
                # (Can't verify Elite without header analysis)
                agg.anonymity_level = "Anonymous"
                agg.anonymity_score = 60
        elif proxy_worked:
            # Proxy worked but no IP data - assume Anonymous as safe default
            # Rationale: Working proxy = at minimum forwarding traffic
            agg.anonymity_level = "Anonymous"
            agg.anonymity_score = 50
        else:
            agg.anonymity_level = "Unknown"
            agg.anonymity_score = 0

    # Cross-validate: If any detected IP matches real IP, it's Transparent
    if real_ip and real_ip in detected_ips:
        agg.anonymity_level = "Transparent"
        agg.real_ip_exposed = True
        agg.anonymity_score = min(agg.anonymity_score, 20)

    return agg
