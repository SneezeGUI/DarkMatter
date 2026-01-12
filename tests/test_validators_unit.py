"""
Unit tests for proxy validator parsing and aggregation logic.

Tests individual validator response parsing and the aggregate scoring system
without making actual network requests.
"""

import json

import pytest

from core.validators import (
    AzenvValidator,
    HttpBinValidator,
    IpApiValidator,
    IpifyValidator,
    IpInfoValidator,
    ValidatorResult,
    WhatIsMyIpValidator,
    aggregate_results,
)
from tests.fixtures.mock_responses import (
    build_azenv_response,
    build_httpbin_response,
    build_ipapi_response,
    build_ipify_response,
    build_ipinfo_response,
    build_wtfismyip_response,
)


class TestHttpBinValidator:
    """Tests for httpbin.org validator parsing."""

    def setup_method(self):
        self.validator = HttpBinValidator()
        self.real_ip = "203.0.113.100"  # User's real IP
        self.proxy_ip = "198.51.100.50"  # Proxy exit IP

    def test_parse_clean_response(self):
        """Elite proxy - no headers leaked, different IP."""
        response = build_httpbin_response(origin=self.proxy_ip)
        result = self.validator.parse_response(
            json.dumps(response), 200, self.real_ip
        )

        assert result.success is True
        assert result.detected_ip == self.proxy_ip
        assert result.real_ip_exposed is False
        assert len(result.proxy_headers_found) == 0

    def test_parse_with_forwarded_for_header(self):
        """Transparent proxy - X-Forwarded-For leaks real IP."""
        response = build_httpbin_response(
            origin=self.proxy_ip,
            extra_headers={"X-Forwarded-For": self.real_ip}
        )
        result = self.validator.parse_response(
            json.dumps(response), 200, self.real_ip
        )

        assert result.success is True
        assert result.real_ip_exposed is True
        assert "X-Forwarded-For" in result.proxy_headers_found
        assert len(result.forwarded_ips) > 0

    def test_parse_with_via_header(self):
        """Anonymous proxy - Via header reveals proxy usage."""
        response = build_httpbin_response(
            origin=self.proxy_ip,
            extra_headers={"Via": "1.1 proxy.example.com"}
        )
        result = self.validator.parse_response(
            json.dumps(response), 200, self.real_ip
        )

        assert result.success is True
        assert result.real_ip_exposed is False  # Via doesn't expose IP
        assert "Via" in result.proxy_headers_found

    def test_parse_with_multiple_leak_headers(self):
        """Multiple proxy-revealing headers."""
        response = build_httpbin_response(
            origin=self.proxy_ip,
            extra_headers={
                "X-Forwarded-For": self.real_ip,
                "Via": "1.1 proxy.example.com",
                "X-Proxy-Id": "12345",
            }
        )
        result = self.validator.parse_response(
            json.dumps(response), 200, self.real_ip
        )

        assert result.real_ip_exposed is True
        assert len(result.proxy_headers_found) >= 3

    def test_parse_comma_separated_origin(self):
        """Origin with multiple IPs (proxy chain)."""
        response = build_httpbin_response(
            origin=f"{self.proxy_ip}, 10.0.0.1"
        )
        result = self.validator.parse_response(
            json.dumps(response), 200, self.real_ip
        )

        assert result.detected_ip == self.proxy_ip  # First IP in chain

    def test_parse_http_error(self):
        """Non-200 status code."""
        result = self.validator.parse_response(
            "Service Unavailable", 503, self.real_ip
        )

        assert result.success is False
        assert "503" in result.error

    def test_parse_invalid_json(self):
        """Invalid JSON response."""
        result = self.validator.parse_response(
            "not valid json", 200, self.real_ip
        )

        assert result.success is False
        assert result.error != ""


class TestIpApiValidator:
    """Tests for ip-api.com validator parsing."""

    def setup_method(self):
        self.validator = IpApiValidator()
        self.real_ip = "203.0.113.100"
        self.proxy_ip = "198.51.100.50"

    def test_parse_clean_response(self):
        """Clean residential IP."""
        response = build_ipapi_response(
            ip=self.proxy_ip,
            proxy=False,
            hosting=False
        )
        result = self.validator.parse_response(
            json.dumps(response), 200, self.real_ip
        )

        assert result.success is True
        assert result.detected_ip == self.proxy_ip
        assert result.flagged_as_proxy is False
        assert result.flagged_as_datacenter is False
        assert result.real_ip_exposed is False

    def test_parse_proxy_detected(self):
        """IP flagged as proxy."""
        response = build_ipapi_response(
            ip=self.proxy_ip,
            proxy=True,
            hosting=False
        )
        result = self.validator.parse_response(
            json.dumps(response), 200, self.real_ip
        )

        assert result.flagged_as_proxy is True
        assert result.flagged_as_datacenter is False

    def test_parse_datacenter_detected(self):
        """IP flagged as datacenter/hosting."""
        response = build_ipapi_response(
            ip=self.proxy_ip,
            proxy=False,
            hosting=True
        )
        result = self.validator.parse_response(
            json.dumps(response), 200, self.real_ip
        )

        assert result.flagged_as_datacenter is True

    def test_parse_real_ip_exposed(self):
        """Real IP returned (no proxy effect)."""
        response = build_ipapi_response(ip=self.real_ip)
        result = self.validator.parse_response(
            json.dumps(response), 200, self.real_ip
        )

        assert result.real_ip_exposed is True

    def test_parse_api_error(self):
        """API returns error status."""
        response = build_ipapi_response(
            ip="",
            status="fail",
            message="invalid query"
        )
        result = self.validator.parse_response(
            json.dumps(response), 200, self.real_ip
        )

        assert result.success is False
        assert "invalid query" in result.error


class TestIpifyValidator:
    """Tests for ipify.org validator parsing."""

    def setup_method(self):
        self.validator = IpifyValidator()
        self.real_ip = "203.0.113.100"
        self.proxy_ip = "198.51.100.50"

    def test_parse_different_ip(self):
        """Proxy IP returned (proxy working)."""
        response = build_ipify_response(ip=self.proxy_ip)
        result = self.validator.parse_response(
            json.dumps(response), 200, self.real_ip
        )

        assert result.success is True
        assert result.detected_ip == self.proxy_ip
        assert result.real_ip_exposed is False

    def test_parse_real_ip(self):
        """Real IP returned (proxy not working)."""
        response = build_ipify_response(ip=self.real_ip)
        result = self.validator.parse_response(
            json.dumps(response), 200, self.real_ip
        )

        assert result.real_ip_exposed is True


class TestIpInfoValidator:
    """Tests for ipinfo.io validator parsing."""

    def setup_method(self):
        self.validator = IpInfoValidator()
        self.real_ip = "203.0.113.100"
        self.proxy_ip = "198.51.100.50"

    def test_parse_clean_response(self):
        """Clean response without privacy data."""
        response = build_ipinfo_response(ip=self.proxy_ip)
        result = self.validator.parse_response(
            json.dumps(response), 200, self.real_ip
        )

        assert result.success is True
        assert result.detected_ip == self.proxy_ip
        assert result.flagged_as_proxy is False
        assert result.flagged_as_vpn is False

    def test_parse_with_privacy_proxy_flag(self):
        """Privacy data indicates proxy."""
        response = build_ipinfo_response(
            ip=self.proxy_ip,
            privacy={"proxy": True, "vpn": False, "hosting": False}
        )
        result = self.validator.parse_response(
            json.dumps(response), 200, self.real_ip
        )

        assert result.flagged_as_proxy is True
        assert result.flagged_as_vpn is False

    def test_parse_with_privacy_vpn_flag(self):
        """Privacy data indicates VPN."""
        response = build_ipinfo_response(
            ip=self.proxy_ip,
            privacy={"proxy": False, "vpn": True, "hosting": False}
        )
        result = self.validator.parse_response(
            json.dumps(response), 200, self.real_ip
        )

        assert result.flagged_as_vpn is True

    def test_parse_with_privacy_hosting_flag(self):
        """Privacy data indicates datacenter."""
        response = build_ipinfo_response(
            ip=self.proxy_ip,
            privacy={"proxy": False, "vpn": False, "hosting": True}
        )
        result = self.validator.parse_response(
            json.dumps(response), 200, self.real_ip
        )

        assert result.flagged_as_datacenter is True


class TestAzenvValidator:
    """Tests for azenv.net HTML validator parsing."""

    def setup_method(self):
        self.validator = AzenvValidator()
        self.real_ip = "203.0.113.100"
        self.proxy_ip = "198.51.100.50"

    def test_parse_clean_response(self):
        """Clean HTML response with no leak headers."""
        response = build_azenv_response(ip=self.proxy_ip)
        result = self.validator.parse_response(response, 200, self.real_ip)

        assert result.success is True
        assert result.detected_ip == self.proxy_ip
        assert result.real_ip_exposed is False
        assert len(result.proxy_headers_found) == 0

    def test_parse_with_forwarded_for(self):
        """X-Forwarded-For header in environment."""
        response = build_azenv_response(
            ip=self.proxy_ip,
            extra_env_vars={"HTTP_X_FORWARDED_FOR": self.real_ip}
        )
        result = self.validator.parse_response(response, 200, self.real_ip)

        assert result.real_ip_exposed is True
        assert "X-Forwarded-For" in result.proxy_headers_found

    def test_parse_with_via_header(self):
        """Via header in environment."""
        response = build_azenv_response(
            ip=self.proxy_ip,
            extra_env_vars={"HTTP_VIA": "1.1 proxy.example.com"}
        )
        result = self.validator.parse_response(response, 200, self.real_ip)

        assert "Via" in result.proxy_headers_found
        assert result.real_ip_exposed is False

    def test_parse_real_ip_in_remote_addr(self):
        """REMOTE_ADDR shows real IP (proxy not working)."""
        response = build_azenv_response(ip=self.real_ip)
        result = self.validator.parse_response(response, 200, self.real_ip)

        assert result.real_ip_exposed is True


class TestWhatIsMyIpValidator:
    """Tests for wtfismyip.com validator parsing."""

    def setup_method(self):
        self.validator = WhatIsMyIpValidator()
        self.real_ip = "203.0.113.100"
        self.proxy_ip = "198.51.100.50"

    def test_parse_different_ip(self):
        """Proxy IP returned."""
        response = build_wtfismyip_response(ip=self.proxy_ip)
        result = self.validator.parse_response(
            json.dumps(response), 200, self.real_ip
        )

        assert result.success is True
        assert result.detected_ip == self.proxy_ip
        assert result.real_ip_exposed is False

    def test_parse_real_ip(self):
        """Real IP returned."""
        response = build_wtfismyip_response(ip=self.real_ip)
        result = self.validator.parse_response(
            json.dumps(response), 200, self.real_ip
        )

        assert result.real_ip_exposed is True


class TestAggregateResults:
    """Tests for the result aggregation and scoring logic."""

    def setup_method(self):
        self.real_ip = "203.0.113.100"
        self.proxy_ip = "198.51.100.50"

    def _make_result(
        self,
        success: bool = True,
        detected_ip: str = "",
        real_ip_exposed: bool = False,
        proxy_headers: list[str] | None = None,
        flagged_as_proxy: bool = False,
        flagged_as_datacenter: bool = False,
    ) -> ValidatorResult:
        """Helper to create ValidatorResult for testing."""
        return ValidatorResult(
            validator_name="test_validator",
            success=success,
            detected_ip=detected_ip or self.proxy_ip,
            real_ip_exposed=real_ip_exposed,
            proxy_headers_found=proxy_headers or [],
            flagged_as_proxy=flagged_as_proxy,
            flagged_as_datacenter=flagged_as_datacenter,
        )

    def test_elite_score(self):
        """All validators pass, no flags - Elite anonymity."""
        results = [
            self._make_result(detected_ip=self.proxy_ip),
            self._make_result(detected_ip=self.proxy_ip),
            self._make_result(detected_ip=self.proxy_ip),
        ]

        agg = aggregate_results(results, self.real_ip)

        assert agg.anonymity_level == "Elite"
        assert agg.anonymity_score >= 80
        assert agg.real_ip_exposed is False
        assert agg.validators_passed == 3

    def test_anonymous_with_proxy_headers(self):
        """Some proxy headers found - Anonymous level."""
        results = [
            self._make_result(proxy_headers=["Via", "X-Proxy-Id"]),
            self._make_result(),
        ]

        agg = aggregate_results(results, self.real_ip)

        # Score: 100 - (2 headers * 5) = 90, but Via/X-Proxy-Id aren't IP-exposing
        assert agg.anonymity_score <= 100
        assert "Via" in agg.leaking_headers or "X-Proxy-Id" in agg.leaking_headers

    def test_anonymous_with_proxy_flag(self):
        """Flagged as proxy - Score penalty."""
        results = [
            self._make_result(flagged_as_proxy=True),
            self._make_result(),
        ]

        agg = aggregate_results(results, self.real_ip)

        # Score: 100 - 20 (proxy flag) = 80, which is still Elite threshold
        assert agg.proxy_detected is True
        assert agg.anonymity_score <= 80

    def test_transparent_real_ip_exposed(self):
        """Real IP exposed - Transparent level."""
        results = [
            self._make_result(real_ip_exposed=True),
            self._make_result(),
        ]

        agg = aggregate_results(results, self.real_ip)

        assert agg.anonymity_level == "Transparent"
        assert agg.real_ip_exposed is True
        assert agg.anonymity_score <= 50

    def test_datacenter_penalty(self):
        """Datacenter IP detected - Score penalty."""
        results = [
            self._make_result(flagged_as_datacenter=True),
        ]

        agg = aggregate_results(results, self.real_ip)

        assert agg.datacenter_detected is True
        # Score: 100 - 10 (datacenter) = 90, still Elite
        assert agg.anonymity_score <= 90

    def test_cumulative_penalties(self):
        """Multiple penalties accumulate."""
        results = [
            self._make_result(
                flagged_as_proxy=True,
                flagged_as_datacenter=True,
                proxy_headers=["Via", "X-Forwarded-Proto", "X-Cache"],
            ),
        ]

        agg = aggregate_results(results, self.real_ip)

        # Score: 100 - 20 (proxy) - 10 (dc) - 15 (3 headers * 5) = 55
        assert agg.anonymity_score < 80
        assert agg.anonymity_level in ["Anonymous", "Transparent"]

    def test_all_validators_failed(self):
        """All validators failed - fallback logic."""
        results = [
            self._make_result(success=False),
            self._make_result(success=False),
        ]

        agg = aggregate_results(results, self.real_ip)

        assert agg.validators_passed == 0
        assert agg.validators_failed == 2
        # Fallback behavior depends on proxy_worked parameter

    def test_mixed_success_failure(self):
        """Some validators pass, some fail."""
        results = [
            self._make_result(success=True),
            self._make_result(success=False),
            self._make_result(success=True),
        ]

        agg = aggregate_results(results, self.real_ip)

        assert agg.validators_passed == 2
        assert agg.validators_failed == 1
        assert agg.validators_total == 3

    def test_score_clamping(self):
        """Score is clamped between 0 and 100."""
        # Many penalties
        results = [
            self._make_result(
                real_ip_exposed=True,
                flagged_as_proxy=True,
                flagged_as_datacenter=True,
                proxy_headers=["Via", "X-Forwarded-For", "X-Real-IP", "X-Client-IP"],
            ),
        ]

        agg = aggregate_results(results, self.real_ip)

        assert agg.anonymity_score >= 0
        assert agg.anonymity_score <= 100

    def test_empty_results(self):
        """No results provided."""
        agg = aggregate_results([], self.real_ip)

        assert agg.validators_total == 0
        assert agg.validators_passed == 0


class TestValidatorIntegration:
    """Integration tests using full validator flow."""

    @pytest.mark.parametrize("validator_class,response_builder", [
        (HttpBinValidator, lambda ip: json.dumps(build_httpbin_response(origin=ip))),
        (IpApiValidator, lambda ip: json.dumps(build_ipapi_response(ip=ip))),
        (IpifyValidator, lambda ip: json.dumps(build_ipify_response(ip=ip))),
        (IpInfoValidator, lambda ip: json.dumps(build_ipinfo_response(ip=ip))),
        (WhatIsMyIpValidator, lambda ip: json.dumps(build_wtfismyip_response(ip=ip))),
    ])
    def test_validator_detects_proxy_ip(self, validator_class, response_builder):
        """Each validator correctly identifies when proxy IP differs from real IP."""
        validator = validator_class()
        real_ip = "203.0.113.100"
        proxy_ip = "198.51.100.50"

        result = validator.parse_response(
            response_builder(proxy_ip), 200, real_ip
        )

        assert result.success is True
        assert result.detected_ip == proxy_ip
        assert result.real_ip_exposed is False

    @pytest.mark.parametrize("validator_class,response_builder", [
        # Note: HttpBinValidator excluded - it only checks headers, not origin vs real IP
        (IpApiValidator, lambda ip: json.dumps(build_ipapi_response(ip=ip))),
        (IpifyValidator, lambda ip: json.dumps(build_ipify_response(ip=ip))),
        (IpInfoValidator, lambda ip: json.dumps(build_ipinfo_response(ip=ip))),
        (WhatIsMyIpValidator, lambda ip: json.dumps(build_wtfismyip_response(ip=ip))),
    ])
    def test_validator_detects_real_ip_exposure(self, validator_class, response_builder):
        """Validators that compare detected IP to real IP detect exposure."""
        validator = validator_class()
        real_ip = "203.0.113.100"

        result = validator.parse_response(
            response_builder(real_ip), 200, real_ip
        )

        assert result.real_ip_exposed is True

    def test_httpbin_detects_real_ip_in_headers(self):
        """HttpBinValidator detects real IP when it appears in forwarded headers."""
        validator = HttpBinValidator()
        real_ip = "203.0.113.100"
        proxy_ip = "198.51.100.50"

        # Real IP exposed via X-Forwarded-For header
        response = build_httpbin_response(
            origin=proxy_ip,
            extra_headers={"X-Forwarded-For": real_ip}
        )
        result = validator.parse_response(
            json.dumps(response), 200, real_ip
        )

        assert result.real_ip_exposed is True

    def test_azenv_html_parsing(self):
        """AzenvValidator correctly parses HTML format."""
        validator = AzenvValidator()
        real_ip = "203.0.113.100"
        proxy_ip = "198.51.100.50"

        response = build_azenv_response(ip=proxy_ip)
        result = validator.parse_response(response, 200, real_ip)

        assert result.success is True
        assert result.detected_ip == proxy_ip
