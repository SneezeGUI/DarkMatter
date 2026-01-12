"""
Unit tests for the browser engine module (core/browser_engine.py).
Covers stealth script generation, proxy filtering logic, and protection detection.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.browser_engine import (
    generate_stealth_script,
    PlaywrightTrafficEngine,
    OS_PROFILES
)
from core.models import ProxyConfig
from tests.fixtures.mock_responses import build_proxy_config

# =============================================================================
# Stealth Script Generation Tests
# =============================================================================

class TestStealthScriptGenerator:
    """Tests for the generate_stealth_script function."""

    def test_generate_script_windows_chrome(self):
        """Test script generation for Windows Chrome profile."""
        profile = next(p for p in OS_PROFILES if p["name"] == "Windows Chrome")
        script = generate_stealth_script(profile, session_seed=12345)

        assert "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })" in script
        assert "Object.defineProperty(navigator, 'platform', { get: () => 'Win32' })" in script
        assert "window.chrome = {" in script
        assert "Object.defineProperty(navigator, 'userAgentData'" in script

    def test_generate_script_firefox(self):
        """Test script generation for Firefox profile."""
        profile = next(p for p in OS_PROFILES if "Firefox" in p["name"])
        script = generate_stealth_script(profile, session_seed=12345)

        assert "Object.defineProperty(navigator, 'oscpu', { get: () =>" in script
        assert "window.chrome" not in script
        # Firefox specific plugin spoofing
        assert "Object.defineProperty(navigator, 'plugins', {" in script

    def test_generate_script_macos_safari(self):
        """Test script generation for macOS Safari (Webkit) profile."""
        profile = next(p for p in OS_PROFILES if "Safari" in p["name"])
        script = generate_stealth_script(profile, session_seed=12345)

        assert "MacIntel" in script
        assert "Apple Computer, Inc." in script
        # WebKit specific plugin spoofing
        assert "Object.defineProperty(navigator, 'plugins', {" in script

    def test_script_determinism(self):
        """Test that the same seed produces identical scripts (deterministic noise)."""
        profile = OS_PROFILES[0]
        
        # We need to patch random because the function uses random.uniform() 
        # for noise constants even if session_seed is provided.
        with patch('random.uniform', side_effect=[0.1, 0.2, 0.3, 0.1, 0.2, 0.3]):
            script1 = generate_stealth_script(profile, session_seed=999)
            script2 = generate_stealth_script(profile, session_seed=999)
            
            assert script1 == script2

    def test_script_uniqueness_with_seeds(self):
        """Test that different seeds produce different scripts (noise variation)."""
        profile = OS_PROFILES[0]
        script1 = generate_stealth_script(profile, session_seed=1)
        script2 = generate_stealth_script(profile, session_seed=2)
        
        # The constants injected for noise should differ
        assert script1 != script2
        assert "const _sessionSeed = 1;" in script1
        assert "const _sessionSeed = 2;" in script2

    def test_session_seed_generation_if_none(self):
        """Test that a seed is generated if None is provided."""
        profile = OS_PROFILES[0]
        script = generate_stealth_script(profile, session_seed=None)
        assert "const _sessionSeed =" in script


# =============================================================================
# Browser Proxy Filtering Tests
# =============================================================================

class TestBrowserProxyFiltering:
    """Tests for PlaywrightTrafficEngine._filter_browser_proxies."""

    def test_prioritize_socks_proxies(self):
        """Test that SOCKS5 and SOCKS4 are prioritized over HTTP."""
        proxies = [
            build_proxy_config(host="1.1.1.1", port=8080, protocol="http"),
            build_proxy_config(host="2.2.2.2", port=1080, protocol="socks5"),
            build_proxy_config(host="3.3.3.3", port=1080, protocol="socks4"),
        ]

        filtered = PlaywrightTrafficEngine._filter_browser_proxies(proxies)
        
        assert len(filtered) == 3
        assert filtered[0].protocol == "socks5"
        assert filtered[1].protocol == "socks4"
        assert filtered[2].protocol == "http"

    def test_filter_port_80_http(self):
        """Test that HTTP proxies on port 80 are filtered out."""
        proxies = [
            build_proxy_config(host="1.1.1.1", port=80, protocol="http"),
            build_proxy_config(host="2.2.2.2", port=8080, protocol="http"),
        ]

        filtered = PlaywrightTrafficEngine._filter_browser_proxies(proxies)
        
        assert len(filtered) == 1
        assert filtered[0].port == 8080

    def test_keep_https_capable_ports(self):
        """Test that common HTTPS proxy ports are kept."""
        common_ports = [8080, 3128, 8888, 8118, 443]
        proxies = [
            build_proxy_config(host=f"1.1.1.{i}", port=port, protocol="http")
            for i, port in enumerate(common_ports)
        ]

        filtered = PlaywrightTrafficEngine._filter_browser_proxies(proxies)
        assert len(filtered) == len(common_ports)

    def test_empty_proxy_list(self):
        """Test handling of empty proxy list."""
        assert PlaywrightTrafficEngine._filter_browser_proxies([]) == []

    def test_mixed_protocol_sorting(self):
        """Test complex sorting with mixed protocols and ports."""
        proxies = [
            build_proxy_config(host="1.1", port=80, protocol="http"),      # Should be removed
            build_proxy_config(host="2.2", port=1234, protocol="http"),    # 'Other' http
            build_proxy_config(host="3.3", port=8080, protocol="http"),    # Common http
            build_proxy_config(host="4.4", port=1080, protocol="socks5"),  # SOCKS5
        ]

        filtered = PlaywrightTrafficEngine._filter_browser_proxies(proxies)

        assert len(filtered) == 3
        assert filtered[0].protocol == "socks5"  # SOCKS5 first
        assert filtered[1].port == 8080          # Common HTTP second
        assert filtered[2].port == 1234          # Other HTTP last
        # Port 80 removed


# =============================================================================
# Protection Detection Tests
# =============================================================================

class TestProtectionDetection:
    """Tests for PlaywrightTrafficEngine._detect_protection logic."""

    def setup_method(self):
        """Setup mock engine and page."""
        self.mock_config = MagicMock()
        self.mock_config.browser.get_executable_path.return_value = None
        self.mock_config.target_url = "https://example.com"

        # Mock Playwright availability
        with patch("core.browser_engine.playwright_available", True):
            # We need to mock the constructor to avoid actual Playwright init
            with patch("core.browser_engine.async_playwright"):
                 self.engine = PlaywrightTrafficEngine(self.mock_config, [])
        
        # Mock Page object
        self.mock_page = AsyncMock()
        self.mock_page.title.return_value = "Normal Page"
        self.mock_page.content.return_value = "<html><body>Some content</body></html>"

    @pytest.mark.asyncio
    async def test_detect_no_protection(self):
        """Test detection on a clean page."""
        prot_type, site_key = await self.engine._detect_protection(self.mock_page)
        
        assert prot_type is None
        assert site_key is None

    @pytest.mark.asyncio
    async def test_detect_cloudflare_strong_signal(self):
        """Test Cloudflare detection via strong signal markers."""
        self.mock_page.content.return_value = "<html><body>... challenge-platform ...</body></html>"
        
        # Mock extract_turnstile_key to return None for this test
        self.engine._extract_turnstile_key = AsyncMock(return_value=None)
        
        prot_type, site_key = await self.engine._detect_protection(self.mock_page)
        
        assert prot_type == "cloudflare"

    @pytest.mark.asyncio
    async def test_detect_cloudflare_multiple_markers(self):
        """Test Cloudflare detection via multiple weak markers."""
        # 'cf-browser-verification' and 'Just a moment...' are markers
        self.mock_page.content.return_value = "<html><body>cf-browser-verification ... Just a moment...</body></html>"
        self.engine._extract_turnstile_key = AsyncMock(return_value=None)

        prot_type, site_key = await self.engine._detect_protection(self.mock_page)
        
        assert prot_type == "cloudflare"

    @pytest.mark.asyncio
    async def test_detect_cloudflare_title_match(self):
        """Test Cloudflare detection via title and one marker."""
        self.mock_page.title.return_value = "Just a moment..."
        self.mock_page.content.return_value = "<html><body>... Ray ID: ...</body></html>"
        self.engine._extract_turnstile_key = AsyncMock(return_value=None)

        prot_type, site_key = await self.engine._detect_protection(self.mock_page)
        
        assert prot_type == "cloudflare"

    @pytest.mark.asyncio
    async def test_detect_akamai(self):
        """Test Akamai detection."""
        # Needs at least 2 Akamai markers
        self.mock_page.content.return_value = "<html><body>... _abck ... ak_bmsc ...</body></html>"

        prot_type, site_key = await self.engine._detect_protection(self.mock_page)
        
        assert prot_type == "akamai"
        assert site_key is None

    @pytest.mark.asyncio
    async def test_detect_recaptcha(self):
        """Test generic reCAPTCHA detection."""
        self.mock_page.content.return_value = "<html><body>... g-recaptcha ...</body></html>"
        
        # Mock finding the site key element
        mock_element = AsyncMock()
        mock_element.get_attribute.return_value = "6Le-dummy-site-key"
        self.mock_page.query_selector.return_value = mock_element

        prot_type, site_key = await self.engine._detect_protection(self.mock_page)
        
        assert prot_type == "captcha"
        assert site_key == "6Le-dummy-site-key"
        self.mock_page.query_selector.assert_called_with(".g-recaptcha[data-sitekey]")

    @pytest.mark.asyncio
    async def test_detect_hcaptcha(self):
        """Test hCaptcha detection."""
        self.mock_page.content.return_value = "<html><body>... h-captcha ...</body></html>"
        
        # Mock finding the site key element
        mock_element = AsyncMock()
        mock_element.get_attribute.return_value = "dummy-hcaptcha-key"
        
        # First call (recaptcha) returns None, second (hcaptcha) returns element
        def side_effect(selector):
            if "h-captcha" in selector:
                return mock_element
            return None
            
        self.mock_page.query_selector.side_effect = side_effect

        prot_type, site_key = await self.engine._detect_protection(self.mock_page)
        
        assert prot_type == "captcha"
        assert site_key == "dummy-hcaptcha-key"

    @pytest.mark.asyncio
    async def test_detect_cloudflare_with_turnstile_key(self):
        """Test Cloudflare detection that also finds a Turnstile key."""
        self.mock_page.content.return_value = "<html><body>... challenge-platform ...</body></html>"
        
        # Mock _extract_turnstile_key
        self.engine._extract_turnstile_key = AsyncMock(return_value="0x4AAAAAAAAAI")

        prot_type, site_key = await self.engine._detect_protection(self.mock_page)
        
        assert prot_type == "cloudflare"
        assert site_key == "0x4AAAAAAAAAI"
