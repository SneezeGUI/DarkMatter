"""
Browser-based traffic engine using Playwright.
Provides realistic browser automation with protection bypass capabilities.
Matches AsyncTrafficEngine interface for UI compatibility.
Supports Chrome, Edge, Brave (Chromium) and Firefox browsers.
"""

import asyncio
import contextlib
import logging
import random
import re
from collections.abc import Callable
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from .browser_manager import BrowserManager

if TYPE_CHECKING:
    from .session_manager import SessionManager
from .constants import (
    AKAMAI_MARKERS,
    BROWSER_VIEWPORTS,
    CAPTCHA_MARKERS,
    CLOUDFLARE_MARKERS,
    CLOUDFLARE_TITLE_MARKERS,
    OS_PROFILES,
    SUCCESS_STATUS_CODES,
    get_referers,
)
from .models import ProxyConfig, TrafficConfig, TrafficStats

# Playwright imports are done lazily to avoid import errors if not installed
playwright_available = False
try:
    from playwright.async_api import (
        Browser,
        BrowserContext,
        Page,
        Playwright,
        async_playwright,
    )

    playwright_available = True
except ImportError:
    pass


def generate_stealth_script(profile: dict, session_seed: int = None) -> str:
    """
    Generate a stealth script customized for the given OS profile.
    Ensures all navigator properties are consistent with the User-Agent.
    Adds fingerprint noise for unique session identification.

    Args:
        profile: OS profile dictionary
        session_seed: Optional seed for deterministic noise (for debugging)
    """
    import random as _random

    if session_seed is None:
        session_seed = _random.randint(1, 2**31)

    languages_js = str(profile.get("languages", ["en-US", "en"])).replace("'", '"')
    webgl_vendor = profile.get("webgl_vendor", "Intel Inc.")
    webgl_renderer = profile.get("webgl_renderer", "Intel Iris OpenGL Engine")
    platform = profile.get("platform", "Win32")
    vendor = profile.get("vendor", "Google Inc.")
    hardware_concurrency = profile.get("hardware_concurrency", 8)
    device_memory = profile.get("device_memory")
    max_touch_points = profile.get("max_touch_points", 0)
    screen_depth = profile.get("screen_depth", 24)
    browser_type = profile.get("browser_type", "chromium")

    # Generate unique noise values for this session
    canvas_noise = _random.uniform(0.0001, 0.001)
    audio_noise = _random.uniform(0.0000001, 0.000001)
    rect_noise = _random.uniform(0.00001, 0.0001)

    # Base script for all browsers
    base_script = f"""
// Remove webdriver flag
Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});

// Spoof platform to match User-Agent
Object.defineProperty(navigator, 'platform', {{ get: () => '{platform}' }});

// Spoof vendor
Object.defineProperty(navigator, 'vendor', {{ get: () => '{vendor}' }});

// Spoof hardware concurrency (CPU cores)
Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {hardware_concurrency} }});

// Spoof max touch points
Object.defineProperty(navigator, 'maxTouchPoints', {{ get: () => {max_touch_points} }});

// Spoof screen color depth
Object.defineProperty(screen, 'colorDepth', {{ get: () => {screen_depth} }});
Object.defineProperty(screen, 'pixelDepth', {{ get: () => {screen_depth} }});

// Fake languages
Object.defineProperty(navigator, 'languages', {{
    get: () => {languages_js}
}});

// Fix permissions query
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({{ state: Notification.permission }}) :
        originalQuery(parameters)
);

// WebGL vendor/renderer spoofing
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {{
    if (parameter === 37445) return '{webgl_vendor}';
    if (parameter === 37446) return '{webgl_renderer}';
    return getParameter.apply(this, arguments);
}};

// WebGL2 spoofing
if (typeof WebGL2RenderingContext !== 'undefined') {{
    const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function(parameter) {{
        if (parameter === 37445) return '{webgl_vendor}';
        if (parameter === 37446) return '{webgl_renderer}';
        return getParameter2.apply(this, arguments);
    }};
}}

// ===== FINGERPRINT UNIQUENESS - Session-specific noise =====
// Unique session seed for deterministic but unique fingerprints
const _sessionSeed = {session_seed};
const _canvasNoise = {canvas_noise};
const _audioNoise = {audio_noise};
const _rectNoise = {rect_noise};

// Simple seeded random for consistent noise within session
function _seededRandom(seed) {{
    const x = Math.sin(seed++) * 10000;
    return x - Math.floor(x);
}}

// Canvas fingerprint noise - adds imperceptible variations to canvas data
const _origToDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function(type) {{
    const ctx = this.getContext('2d');
    if (ctx) {{
        const imageData = ctx.getImageData(0, 0, this.width, this.height);
        const data = imageData.data;
        // Add subtle noise to a few pixels based on session seed
        for (let i = 0; i < Math.min(10, data.length / 4); i++) {{
            const idx = (Math.floor(_seededRandom(_sessionSeed + i) * data.length / 4)) * 4;
            data[idx] = Math.max(0, Math.min(255, data[idx] + Math.floor((_seededRandom(_sessionSeed + idx) - 0.5) * 2)));
        }}
        ctx.putImageData(imageData, 0, 0);
    }}
    return _origToDataURL.apply(this, arguments);
}};

// Canvas getImageData noise
const _origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
CanvasRenderingContext2D.prototype.getImageData = function() {{
    const imageData = _origGetImageData.apply(this, arguments);
    // Add imperceptible noise
    for (let i = 0; i < Math.min(10, imageData.data.length / 4); i++) {{
        const idx = (Math.floor(_seededRandom(_sessionSeed + i) * imageData.data.length / 4)) * 4;
        imageData.data[idx] = Math.max(0, Math.min(255, imageData.data[idx] + Math.floor((_seededRandom(_sessionSeed + idx) - 0.5) * 2)));
    }}
    return imageData;
}};

// AudioContext fingerprint noise
if (typeof AudioBuffer !== 'undefined') {{
    const _origCopyFromChannel = AudioBuffer.prototype.copyFromChannel;
    AudioBuffer.prototype.copyFromChannel = function(dest, channel, start) {{
        _origCopyFromChannel.apply(this, arguments);
        // Add tiny noise to audio data
        for (let i = 0; i < dest.length; i += 100) {{
            dest[i] = dest[i] + (_seededRandom(_sessionSeed + i) - 0.5) * _audioNoise;
        }}
    }};

    const _origGetChannelData = AudioBuffer.prototype.getChannelData;
    AudioBuffer.prototype.getChannelData = function(channel) {{
        const data = _origGetChannelData.apply(this, arguments);
        // Return slightly modified copy
        const copy = new Float32Array(data);
        for (let i = 0; i < copy.length; i += 100) {{
            copy[i] = copy[i] + (_seededRandom(_sessionSeed + i) - 0.5) * _audioNoise;
        }}
        return copy;
    }};
}}

// ClientRect noise - tiny variations in element measurements
const _origGetBoundingClientRect = Element.prototype.getBoundingClientRect;
Element.prototype.getBoundingClientRect = function() {{
    const rect = _origGetBoundingClientRect.apply(this, arguments);
    const noise = _rectNoise * _seededRandom(_sessionSeed + rect.x + rect.y);
    return new DOMRect(
        rect.x + noise,
        rect.y + noise,
        rect.width + noise,
        rect.height + noise
    );
}};

// Date.prototype.getTimezoneOffset noise (very subtle)
const _origGetTimezoneOffset = Date.prototype.getTimezoneOffset;
Date.prototype.getTimezoneOffset = function() {{
    return _origGetTimezoneOffset.apply(this, arguments);
}};

// Performance.now() noise to prevent timing attacks
const _origPerfNow = performance.now;
performance.now = function() {{
    return _origPerfNow.apply(this, arguments) + (_seededRandom(_sessionSeed) * 0.001);
}};
"""

    # Chromium-specific additions
    if browser_type == "chromium":
        chromium_script = f"""
// Add Chrome object
window.chrome = {{
    runtime: {{}},
    loadTimes: function() {{}},
    csi: function() {{}},
    app: {{}}
}};

// Spoof device memory (Chromium only)
Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {device_memory or 8} }});

// Hide automation markers
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;

// Fake plugins (Chrome style)
Object.defineProperty(navigator, 'plugins', {{
    get: () => [1, 2, 3, 4, 5]
}});

// Spoof userAgentData for Client Hints API
if ('userAgentData' in navigator) {{
    Object.defineProperty(navigator, 'userAgentData', {{
        get: () => ({{
            brands: [
                {{ brand: "Not_A Brand", version: "8" }},
                {{ brand: "Chromium", version: "120" }},
                {{ brand: "Google Chrome", version: "120" }}
            ],
            mobile: false,
            platform: "{platform.replace('Win32', 'Windows').replace('MacIntel', 'macOS').replace('Linux x86_64', 'Linux')}"
        }})
    }});
}}
"""
        base_script += chromium_script

    # Firefox-specific additions
    elif browser_type == "firefox":
        oscpu = profile.get("oscpu", "Windows NT 10.0; Win64; x64")
        firefox_script = f"""
// Spoof oscpu (Firefox-specific)
Object.defineProperty(navigator, 'oscpu', {{ get: () => '{oscpu}' }});

// Fake plugins (Firefox style)
Object.defineProperty(navigator, 'plugins', {{
    get: () => ({{
        length: 5,
        item: (i) => null,
        namedItem: (n) => null,
        refresh: () => {{}}
    }})
}});
"""
        base_script += firefox_script

    # WebKit/Safari-specific additions
    elif browser_type == "webkit":
        webkit_script = """
// Fake plugins (Safari style)
Object.defineProperty(navigator, 'plugins', {
    get: () => ({
        length: 5,
        item: (i) => null,
        namedItem: (n) => null,
        refresh: () => {}
    })
});
"""
        base_script += webkit_script

    return base_script


# Legacy compatibility - generate default scripts
CHROMIUM_STEALTH_SCRIPT = generate_stealth_script(OS_PROFILES[0])  # Windows Chrome
FIREFOX_STEALTH_SCRIPT = generate_stealth_script(OS_PROFILES[2])  # Windows Firefox


class PlaywrightTrafficEngine:
    """
    Browser-based traffic engine with Cloudflare/Akamai bypass.
    Uses Playwright for realistic browser automation.
    """

    @staticmethod
    def _filter_browser_proxies(proxies: list[ProxyConfig]) -> list[ProxyConfig]:
        """
        Filter and prioritize proxies for browser mode.

        Browser proxy requirements:
        - SOCKS5/SOCKS4 proxies work well for all traffic
        - HTTPS-capable HTTP proxies (typically port 8080, 3128, etc.)
        - Plain HTTP proxies on port 80 usually CAN'T tunnel HTTPS

        Returns proxies sorted by browser compatibility:
        1. SOCKS5 proxies (best)
        2. SOCKS4 proxies
        3. HTTP proxies on common proxy ports (8080, 3128, etc.)
        4. HTTP proxies on other ports (excluding port 80)
        """
        if not proxies:
            return []

        socks5 = []
        socks4 = []
        http_proxy_ports = []  # Ports commonly used for HTTPS-capable proxies
        http_other = []
        skipped = []

        # Common ports for HTTPS-capable HTTP proxies
        https_capable_ports = {
            8080,
            3128,
            8888,
            8118,
            8000,
            8008,
            8081,
            9080,
            1080,
            443,
        }

        for p in proxies:
            proto = p.protocol.lower() if p.protocol else "http"

            if "socks5" in proto:
                socks5.append(p)
            elif "socks4" in proto:
                socks4.append(p)
            elif p.port in https_capable_ports:
                http_proxy_ports.append(p)
            elif p.port == 80:
                # Port 80 HTTP proxies typically can't tunnel HTTPS
                skipped.append(p)
            else:
                http_other.append(p)

        # Log filtering results
        if skipped:
            logging.debug(
                f"Browser mode: Skipped {len(skipped)} port-80 HTTP proxies (can't tunnel HTTPS)"
            )

        # Return prioritized list
        result = socks5 + socks4 + http_proxy_ports + http_other

        if result:
            logging.info(
                f"Browser mode: Using {len(result)} compatible proxies "
                f"(SOCKS5: {len(socks5)}, SOCKS4: {len(socks4)}, HTTP: {len(http_proxy_ports) + len(http_other)})"
            )
        else:
            logging.warning("Browser mode: No browser-compatible proxies found!")

        return result

    def __init__(
        self,
        config: TrafficConfig,
        proxies: list[ProxyConfig],
        on_update: Callable[[TrafficStats], None] | None = None,
        on_log: Callable[[str], None] | None = None,
        session_manager: "SessionManager | None" = None,
    ):
        """
        Initialize the browser engine.

        Args:
            config: Traffic configuration including browser settings
            proxies: List of proxy configurations
            on_update: Callback for stats updates
            on_log: Callback for log messages to GUI
            session_manager: Optional session manager for cookie persistence
        """
        if not playwright_available:
            raise ImportError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            )

        self.config = config
        self.proxies = self._filter_browser_proxies(list(proxies))  # Filter and copy
        self.on_update = on_update
        self.on_log = on_log
        self.session_manager = session_manager
        self.stats = TrafficStats()
        self.running = False
        self._initial_proxy_count = len(proxies)
        self._filtered_proxy_count = len(self.proxies)
        # Extract domain for session management
        self._target_domain = urlparse(config.target_url).netloc

        # Get browser executable path from config
        self._executable_path = config.browser.get_executable_path()

        # Determine browser type from configured path
        self._browser_type = BrowserManager.get_browser_type_from_path(
            self._executable_path or ""
        )

        # Get browser name for display
        browser_info = BrowserManager.get_browser_info_from_path(
            self._executable_path or ""
        )
        self._browser_name = (
            browser_info.name
            if browser_info
            else ("Firefox" if self._browser_type == "firefox" else "Chromium")
        )

        # Playwright objects
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        # Context pool: list of (context, proxy, metadata) tuples
        # metadata = {"created_at": timestamp, "request_count": int, "profile_name": str}
        self._contexts: list[tuple] = []

        # Captcha manager (lazy loaded)
        self._captcha_manager = None

        # Import time for rotation tracking
        import time

        self._time = time

        # Initialize browser info in stats
        self.stats.browser_type = self._browser_name
        self.stats.contexts_total = config.browser.max_contexts

    def _log(self, message: str):
        """Log message to both Python logger and GUI callback."""
        logging.info(message)
        if self.on_log:
            self.on_log(message)

    async def _init_captcha_solver(self):
        """Initialize captcha manager if any provider is configured."""
        if self.config.captcha.has_any_provider():
            try:
                from .captcha_manager import create_captcha_manager

                self._captcha_manager = create_captcha_manager(self.config.captcha)
                if self._captcha_manager:
                    providers = self._captcha_manager.get_available_providers()
                    self._log(f"Captcha solver ready: {', '.join(providers)}")
            except ImportError as e:
                logging.warning(f"Captcha manager not available: {e}")

    async def _update_balances(self):
        """Fetch and update captcha provider balances in stats."""
        if not self._captcha_manager:
            return

        try:
            balances = await self._captcha_manager.get_balances()
            if "2captcha" in balances:
                self.stats.captcha_balance_2captcha = balances["2captcha"]
            if "anticaptcha" in balances:
                self.stats.captcha_balance_anticaptcha = balances["anticaptcha"]
            self._notify_update()
            logging.debug(f"Updated captcha balances: {balances}")
        except Exception as e:
            logging.warning(f"Failed to update captcha balances: {e}")

    async def _balance_check_loop(self):
        """Background task that checks captcha balances every 5 minutes."""
        # Initial balance check
        await self._update_balances()

        while self.running:
            # Wait 5 minutes between checks
            for _ in range(300):  # 300 seconds = 5 minutes
                if not self.running:
                    return
                await asyncio.sleep(1)

            # Check balances
            await self._update_balances()

    async def _launch_browser(self):
        """Launch browser with configured settings. Supports Chrome, Edge, Brave, and Firefox."""
        self._playwright = await async_playwright().start()

        launch_options = {
            "headless": self.config.browser.headless,
        }

        # Use custom browser path if specified
        if self._executable_path:
            launch_options["executable_path"] = self._executable_path
            logging.info(f"Using browser: {self._executable_path}")

        try:
            # Select Playwright browser type based on executable
            if self._browser_type == "firefox":
                self._browser = await self._playwright.firefox.launch(**launch_options)
                self._log("Firefox browser launched successfully")
            else:
                # Chromium covers Chrome, Edge, and Brave
                self._browser = await self._playwright.chromium.launch(**launch_options)
                self._log(f"{self._browser_name} browser launched successfully")
        except Exception as e:
            self._log(f"Failed to launch browser: {e}")
            raise

    async def _create_context(
        self, proxy: ProxyConfig | None = None
    ) -> BrowserContext:
        """
        Create a browser context with realistic fingerprint using OS profiles.

        Args:
            proxy: Optional proxy configuration for this context

        Returns:
            Configured BrowserContext
        """
        # Select an OS profile that matches the current browser type
        browser_type_map = {
            "chromium": ["chromium", "webkit"],
            "firefox": ["firefox"],
            "webkit": ["webkit", "chromium"],
        }
        compatible_types = browser_type_map.get(self._browser_type, ["chromium"])
        compatible_profiles = [
            p for p in OS_PROFILES if p.get("browser_type") in compatible_types
        ]

        # Select a random compatible profile
        os_profile = (
            random.choice(compatible_profiles)
            if compatible_profiles
            else OS_PROFILES[0]
        )

        # Random viewport for variety
        viewport = random.choice(BROWSER_VIEWPORTS)

        context_options = {
            "viewport": {"width": viewport[0], "height": viewport[1]},
            "user_agent": os_profile["user_agent"],
            "locale": self.config.browser.locale,
            "timezone_id": os_profile.get("timezone", self.config.browser.timezone),
            "ignore_https_errors": not self.config.verify_ssl,
            "color_scheme": "light",
            "screen": {"width": viewport[0], "height": viewport[1]},
        }

        # Load persisted cookies from session manager
        if self.session_manager:
            session_data = self.session_manager.get_session(self._target_domain)
            if session_data and session_data.cookies:
                context_options["storage_state"] = {"cookies": session_data.cookies}

        # Add extra HTTP headers for Client Hints (Chromium)
        if os_profile.get("sec_ch_ua"):
            context_options["extra_http_headers"] = {
                "sec-ch-ua": os_profile["sec_ch_ua"],
                "sec-ch-ua-mobile": os_profile.get("sec_ch_ua_mobile", "?0"),
                "sec-ch-ua-platform": os_profile.get("sec_ch_ua_platform", '"Windows"'),
            }

        # Configure proxy if provided
        if proxy:
            proxy_url = f"{proxy.protocol}://{proxy.host}:{proxy.port}"
            context_options["proxy"] = {"server": proxy_url}

            if proxy.username and proxy.password:
                context_options["proxy"]["username"] = proxy.username
                context_options["proxy"]["password"] = proxy.password

        context = await self._browser.new_context(**context_options)

        # Apply stealth scripts with OS profile for consistent fingerprint
        if self.config.browser.stealth_enabled:
            stealth_script = generate_stealth_script(os_profile)
            await context.add_init_script(stealth_script)

        # Create metadata for fingerprint rotation tracking
        metadata = {
            "created_at": self._time.time(),
            "request_count": 0,
            "profile_name": os_profile["name"],
        }

        logging.debug(f"Created context with OS profile: {os_profile['name']}")

        return context, metadata

    async def _detect_protection(self, page: Page) -> tuple:
        """
        Detect if page has bot protection using multiple signals.

        Args:
            page: Playwright page object

        Returns:
            Tuple of (protection_type, site_key, confidence)
            protection_type: "cloudflare", "akamai", "captcha", or None
            site_key: Captcha site key if found, else None
        """
        try:
            content = await page.content()
            title = await page.title()

            # Count Cloudflare markers for confidence scoring
            cf_marker_count = sum(
                1 for marker in CLOUDFLARE_MARKERS if marker in content
            )
            cf_title_match = any(
                marker.lower() in title.lower() for marker in CLOUDFLARE_TITLE_MARKERS
            )

            # Check for Cloudflare challenge page
            # Multiple signals increase confidence
            is_cloudflare = False

            # Strong signals (any one = definite Cloudflare)
            strong_cf_signals = [
                "challenge-platform" in content,
                "__cf_chl_opt" in content,
                "cf_chl_prog" in content,
                "cdn-cgi/challenge-platform" in content,
                "window._cf_chl_opt" in content,
            ]

            if any(strong_cf_signals):
                is_cloudflare = True
                logging.debug("Cloudflare detected via strong signal")
            elif cf_marker_count >= 2:
                is_cloudflare = True
                logging.debug(f"Cloudflare detected via {cf_marker_count} markers")
            elif cf_title_match and cf_marker_count >= 1:
                is_cloudflare = True
                logging.debug("Cloudflare detected via title + marker")

            if is_cloudflare:
                # Check for Turnstile specifically
                site_key = await self._extract_turnstile_key(page)
                return "cloudflare", site_key

            # Check Akamai
            akamai_count = sum(1 for marker in AKAMAI_MARKERS if marker in content)
            if akamai_count >= 2:
                return "akamai", None

            # Check generic captcha (non-Cloudflare)
            for marker in CAPTCHA_MARKERS:
                if marker in content:
                    # Skip if it's Turnstile (handled by Cloudflare)
                    if "cf-turnstile" in marker or "cloudflare" in marker.lower():
                        continue
                    site_key = await self._extract_site_key(page, "recaptcha")
                    if not site_key:
                        site_key = await self._extract_site_key(page, "hcaptcha")
                    if site_key:
                        return "captcha", site_key

        except Exception as e:
            logging.debug(f"Protection detection error: {e}")

        return None, None

    async def _extract_turnstile_key(self, page: Page) -> str | None:
        """Extract Cloudflare Turnstile site key, including from iframes."""
        try:
            # Try direct page first
            selectors = [
                ".cf-turnstile[data-sitekey]",
                "[data-sitekey]",
                "div[data-sitekey]",
            ]

            for selector in selectors:
                element = await page.query_selector(selector)
                if element:
                    key = await element.get_attribute("data-sitekey")
                    if key:
                        logging.debug(f"Found Turnstile key via selector: {selector}")
                        return key

            # Check for Turnstile iframe
            frames = page.frames
            for frame in frames:
                if "challenges.cloudflare.com" in frame.url or "turnstile" in frame.url:
                    try:
                        # Extract from frame URL or content
                        frame_content = await frame.content()
                        if "data-sitekey" in frame_content:
                            # Parse sitekey from frame
                            match = re.search(
                                r'data-sitekey=["\']([^"\']+)["\']', frame_content
                            )
                            if match:
                                logging.debug("Found Turnstile key in iframe")
                                return match.group(1)
                    except Exception:
                        pass

            # Try JavaScript extraction
            try:
                key = await page.evaluate(
                    """
                    () => {
                        // Check for turnstile widget
                        const widget = document.querySelector('.cf-turnstile, [data-sitekey]');
                        if (widget) return widget.getAttribute('data-sitekey');

                        // Check window object
                        if (window.turnstile && window.turnstile.getResponse) {
                            const containers = document.querySelectorAll('[data-sitekey]');
                            if (containers.length > 0) return containers[0].getAttribute('data-sitekey');
                        }

                        return null;
                    }
                """
                )
                if key:
                    logging.debug("Found Turnstile key via JS evaluation")
                    return key
            except Exception:
                pass

        except Exception as e:
            logging.debug(f"Turnstile key extraction error: {e}")

        return None

    async def _extract_site_key(self, page: Page, captcha_type: str) -> str | None:
        """Extract captcha site key from page."""
        try:
            selectors = {
                "turnstile": ".cf-turnstile[data-sitekey], [data-sitekey]",
                "recaptcha": ".g-recaptcha[data-sitekey]",
                "hcaptcha": ".h-captcha[data-sitekey]",
            }

            selector = selectors.get(captcha_type, "[data-sitekey]")
            element = await page.query_selector(selector)

            if element:
                return await element.get_attribute("data-sitekey")

        except Exception as e:
            logging.debug(f"Site key extraction error: {e}")

        return None

    async def _check_cloudflare_bypassed(self, page: Page) -> bool:
        """
        Check if Cloudflare challenge has been successfully bypassed.
        Uses multiple signals for reliable detection.
        """
        try:
            # Check 1: cf_clearance cookie present
            cookies = await page.context.cookies()
            has_clearance = any(c["name"] == "cf_clearance" for c in cookies)

            # Check 2: No challenge markers in content
            content = await page.content()
            has_challenge = any(
                marker in content
                for marker in [
                    "challenge-platform",
                    "__cf_chl_opt",
                    "cf_chl_prog",
                    "cdn-cgi/challenge-platform",
                ]
            )

            # Check 3: Title doesn't indicate challenge
            title = await page.title()
            challenge_title = any(
                marker.lower() in title.lower() for marker in CLOUDFLARE_TITLE_MARKERS
            )

            # Check 4: Page has actual content (not just challenge)
            body_text = await page.evaluate(
                "document.body ? document.body.innerText.length : 0"
            )
            has_content = body_text > 500  # Real pages have substantial content

            # Bypass successful if:
            # - Has clearance cookie, OR
            # - No challenge markers AND no challenge title AND has content
            if has_clearance:
                logging.debug("Cloudflare bypass confirmed via cf_clearance cookie")
                return True

            if not has_challenge and not challenge_title and has_content:
                logging.debug("Cloudflare bypass confirmed via content analysis")
                return True

            return False

        except Exception as e:
            logging.debug(f"Cloudflare bypass check error: {e}")
            return False

    async def _handle_cloudflare(self, page: Page, site_key: str | None) -> bool:
        """
        Handle Cloudflare challenge with multi-stage bypass strategy.

        Strategy:
        1. Wait for JS challenge to auto-resolve (most common)
        2. Simulate human behavior (mouse movement, scrolling)
        3. Look for and interact with Turnstile checkbox
        4. Use captcha solver API as last resort

        Args:
            page: Playwright page
            site_key: Turnstile site key if found

        Returns:
            True if bypass successful
        """
        if not self.config.protection.cloudflare_enabled:
            return False

        # Track detection
        self.stats.cloudflare_detected += 1
        self.stats.last_protection_event = "Cloudflare detected..."
        self._notify_update()

        self._log("Cloudflare challenge detected, attempting bypass...")

        max_wait_seconds = self.config.protection.cloudflare_wait_seconds
        start_time = self._time.time()

        try:
            # ===== STAGE 1: Wait for JavaScript challenge to auto-resolve =====
            self._log("Stage 1: Waiting for JS challenge...")
            self.stats.last_protection_event = "CF: Waiting for JS challenge..."
            self._notify_update()

            # Wait in intervals, checking for bypass between each
            for _wait_round in range(3):
                wait_time = min(3, max_wait_seconds - (self._time.time() - start_time))
                if wait_time <= 0:
                    break

                await asyncio.sleep(wait_time)

                # Check if bypassed
                if await self._check_cloudflare_bypassed(page):
                    elapsed = round(self._time.time() - start_time, 1)
                    self._log(f"Cloudflare JS challenge auto-resolved in {elapsed}s")
                    self.stats.cloudflare_bypassed += 1
                    self.stats.last_protection_event = "CF bypassed (JS auto)"
                    self._notify_update()
                    return True

            # ===== STAGE 2: Simulate human interaction for managed challenge =====
            self._log("Stage 2: Simulating human behavior...")
            self.stats.last_protection_event = "CF: Simulating human..."
            self._notify_update()

            # Simulate mouse movement
            try:
                viewport = page.viewport_size
                if viewport:
                    # Random mouse movements
                    for _ in range(3):
                        x = random.randint(100, viewport["width"] - 100)
                        y = random.randint(100, viewport["height"] - 100)
                        await page.mouse.move(x, y)
                        await asyncio.sleep(random.uniform(0.1, 0.3))

                    # Scroll down slightly
                    await page.evaluate("window.scrollBy(0, 100)")
                    await asyncio.sleep(0.5)
            except Exception as e:
                logging.debug(f"Mouse simulation error: {e}")

            # Wait and check again
            await asyncio.sleep(2)
            if await self._check_cloudflare_bypassed(page):
                elapsed = round(self._time.time() - start_time, 1)
                self._log(f"Cloudflare bypassed after interaction in {elapsed}s")
                self.stats.cloudflare_bypassed += 1
                self.stats.last_protection_event = "CF bypassed (interaction)"
                self._notify_update()
                return True

            # ===== STAGE 3: Try clicking Turnstile checkbox =====
            self._log("Stage 3: Looking for Turnstile checkbox...")
            self.stats.last_protection_event = "CF: Looking for checkbox..."
            self._notify_update()

            turnstile_clicked = await self._try_click_turnstile(page)

            if turnstile_clicked:
                # Wait for verification
                await asyncio.sleep(3)

                if await self._check_cloudflare_bypassed(page):
                    elapsed = round(self._time.time() - start_time, 1)
                    self._log(f"Cloudflare bypassed via checkbox click in {elapsed}s")
                    self.stats.cloudflare_bypassed += 1
                    self.stats.last_protection_event = "CF bypassed (checkbox)"
                    self._notify_update()
                    return True

            # ===== STAGE 4: Use captcha solver API as last resort =====
            if (
                site_key
                and self._captcha_manager
                and self.config.protection.auto_solve_captcha
            ):
                self._log("Stage 4: Using captcha solver API...")
                self.stats.last_protection_event = "CF: Solving Turnstile API..."
                self.stats.captcha_pending += 1
                self._notify_update()

                try:
                    solution = await self._captcha_manager.solve_turnstile(
                        site_key, page.url
                    )
                    self.stats.captcha_pending -= 1

                    if solution.success and solution.token:
                        self.stats.captcha_solved += 1
                        self._log("Turnstile token received, injecting...")

                        # Inject solution token
                        await page.evaluate(
                            f"""
                            () => {{
                                // Try multiple injection methods
                                let injected = false;

                                // Method 1: Direct input field
                                const input = document.querySelector('[name="cf-turnstile-response"]');
                                if (input) {{
                                    input.value = '{solution.token}';
                                    injected = true;
                                }}

                                // Method 2: Hidden textarea
                                const textarea = document.querySelector('textarea[name="cf-turnstile-response"]');
                                if (textarea) {{
                                    textarea.value = '{solution.token}';
                                    injected = true;
                                }}

                                // Method 3: Set via turnstile callback if available
                                if (window.turnstile) {{
                                    try {{
                                        // Find widget ID and set response
                                        const widgets = document.querySelectorAll('.cf-turnstile');
                                        widgets.forEach(w => {{
                                            const widgetId = w.getAttribute('data-widget-id');
                                            if (widgetId && window.turnstile.getResponse) {{
                                                // Trigger callback
                                                const callback = w.getAttribute('data-callback');
                                                if (callback && window[callback]) {{
                                                    window[callback]('{solution.token}');
                                                    injected = true;
                                                }}
                                            }}
                                        }});
                                    }} catch(e) {{}}
                                }}

                                // Method 4: Submit form
                                if (injected) {{
                                    const form = document.querySelector('form');
                                    if (form) {{
                                        setTimeout(() => form.submit(), 500);
                                    }}
                                }}

                                return injected;
                            }}
                        """
                        )

                        await asyncio.sleep(2)

                        # May timeout, that's ok
                        with contextlib.suppress(Exception):
                            await page.wait_for_load_state("networkidle", timeout=10000)

                        # Final verification
                        if await self._check_cloudflare_bypassed(page):
                            elapsed = round(self._time.time() - start_time, 1)
                            self._log(
                                f"Cloudflare bypassed via API solver in {elapsed}s"
                            )
                            self.stats.cloudflare_bypassed += 1
                            self.stats.last_protection_event = "CF bypassed (API solve)"
                            self._notify_update()
                            return True
                        else:
                            self._log(
                                "Turnstile token injected but bypass not confirmed"
                            )
                    else:
                        self.stats.captcha_failed += 1
                        self._log(f"Turnstile solve failed: {solution.error}")

                except Exception as e:
                    self.stats.captcha_pending = max(0, self.stats.captcha_pending - 1)
                    logging.debug(f"Captcha solver error: {e}")

            # ===== All stages failed =====
            elapsed = round(self._time.time() - start_time, 1)
            self._log(f"Cloudflare bypass failed after {elapsed}s")
            self.stats.last_protection_event = "CF bypass failed"
            self._notify_update()
            return False

        except Exception as e:
            logging.debug(f"Cloudflare handling error: {e}")
            self.stats.last_protection_event = f"CF error: {str(e)[:30]}"
            self._notify_update()
            return False

    async def _try_click_turnstile(self, page: Page) -> bool:
        """
        Try to find and click Turnstile checkbox/verification element.

        Returns:
            True if click was attempted
        """
        try:
            # Try to find Turnstile iframe and click inside it
            frames = page.frames
            for frame in frames:
                if "challenges.cloudflare.com" in frame.url:
                    try:
                        # Look for checkbox or verify button
                        selectors = [
                            'input[type="checkbox"]',
                            '[role="checkbox"]',
                            ".cb-lb",  # Turnstile checkbox label
                            "#challenge-stage",
                        ]

                        for selector in selectors:
                            element = await frame.query_selector(selector)
                            if element:
                                # Simulate human-like click with offset
                                box = await element.bounding_box()
                                if box:
                                    x = (
                                        box["x"]
                                        + box["width"] / 2
                                        + random.uniform(-5, 5)
                                    )
                                    y = (
                                        box["y"]
                                        + box["height"] / 2
                                        + random.uniform(-5, 5)
                                    )
                                    await page.mouse.click(x, y)
                                    logging.debug(
                                        f"Clicked Turnstile element: {selector}"
                                    )
                                    return True
                    except Exception as e:
                        logging.debug(f"Frame click error: {e}")

            # Try clicking on main page
            main_selectors = [
                ".cf-turnstile",
                "[data-sitekey]",
                "#turnstile-wrapper",
            ]

            for selector in main_selectors:
                element = await page.query_selector(selector)
                if element:
                    try:
                        await element.click()
                        logging.debug(f"Clicked main page element: {selector}")
                        return True
                    except Exception:
                        pass

        except Exception as e:
            logging.debug(f"Turnstile click error: {e}")

        return False

    def _notify_update(self):
        """Send stats update to callback if registered."""
        if self.on_update:
            self.stats.active_contexts = len(self._contexts)
            self.stats.active_proxies = len(self.proxies)
            self.on_update(self.stats)

    async def _mark_proxy_dead(self, proxy: ProxyConfig, context: BrowserContext):
        """
        Mark a proxy as dead and schedule context for recycling.
        Removes proxy from pool and closes the associated context.
        """
        # Remove from proxy pool
        if proxy in self.proxies:
            try:
                self.proxies.remove(proxy)
                self._log(f"Removed dead proxy {proxy.host}:{proxy.port}")
            except ValueError:
                pass

        # Find and remove the context from our pool
        for i, (ctx, ctx_proxy, _meta) in enumerate(self._contexts):
            if ctx_proxy == proxy:
                with contextlib.suppress(Exception):
                    await ctx.close()
                self._contexts.pop(i)
                logging.debug(
                    f"Closed context for dead proxy {proxy.host}:{proxy.port}"
                )
                break

        # Schedule context recreation if we have spare proxies
        if self.proxies and len(self._contexts) < self.config.browser.max_contexts:
            await self._recycle_context()

    async def _recycle_context(self):
        """Create a new context with an available proxy to replace a dead one."""
        if not self._browser or not self.proxies:
            return

        # Find a proxy not currently in use
        # Use (host, port) tuples as keys since ProxyConfig is not hashable
        used_proxy_keys = {
            (ctx_proxy.host, ctx_proxy.port)
            for _, ctx_proxy, _ in self._contexts
            if ctx_proxy is not None
        }
        available = [p for p in self.proxies if (p.host, p.port) not in used_proxy_keys]

        if not available:
            # All proxies in use, just pick any
            available = self.proxies

        if available:
            proxy = random.choice(available)
            try:
                context, metadata = await self._create_context(proxy)
                self._contexts.append((context, proxy, metadata))
                logging.info(f"Recycled context with proxy {proxy.host}:{proxy.port}")
            except Exception as e:
                logging.debug(f"Failed to recycle context: {e}")

    async def _check_fingerprint_rotation(self):
        """
        Check if any contexts need fingerprint rotation based on request count or time.
        Rotates contexts that exceed thresholds to simulate user closing/reopening browser.
        """
        if not self._contexts:
            return

        rotation_requests = self.config.browser.fingerprint_rotation_requests
        rotation_minutes = self.config.browser.fingerprint_rotation_minutes
        current_time = self._time.time()

        contexts_to_rotate = []

        for i, (_ctx, _proxy, meta) in enumerate(self._contexts):
            # Check request count threshold
            if meta["request_count"] >= rotation_requests:
                contexts_to_rotate.append(i)
                continue

            # Check time threshold (convert minutes to seconds)
            age_seconds = current_time - meta["created_at"]
            if age_seconds >= (rotation_minutes * 60):
                contexts_to_rotate.append(i)

        # Rotate contexts (in reverse order to preserve indices)
        for i in reversed(contexts_to_rotate):
            ctx, proxy, meta = self._contexts[i]
            old_profile = meta.get("profile_name", "Unknown")
            old_requests = meta["request_count"]

            # Close old context
            with contextlib.suppress(Exception):
                await ctx.close()

            # Create new context with fresh fingerprint
            try:
                new_ctx, new_meta = await self._create_context(proxy)
                self._contexts[i] = (new_ctx, proxy, new_meta)
                self._log(
                    f"Rotated fingerprint: {old_profile} ({old_requests} reqs) -> {new_meta['profile_name']}"
                )
            except Exception as e:
                # Remove failed context
                self._contexts.pop(i)
                logging.warning(f"Failed to rotate context: {e}")

    async def _handle_captcha(self, page: Page, site_key: str) -> bool:
        """
        Handle generic captcha challenge.

        Args:
            page: Playwright page
            site_key: Captcha site key

        Returns:
            True if solve successful
        """
        if not self._captcha_manager or not self.config.protection.auto_solve_captcha:
            return False

        # Track captcha detection
        self.stats.captcha_detected += 1
        self.stats.captcha_pending += 1
        self._notify_update()

        try:
            content = await page.content()
            captcha_type = "captcha"

            # Determine captcha type and use appropriate solver
            if "g-recaptcha" in content or "grecaptcha" in content:
                captcha_type = "reCAPTCHA"
                self.stats.last_protection_event = "Solving reCAPTCHA..."
                self._notify_update()
                logging.info("Solving reCAPTCHA...")
                solution = await self._captcha_manager.solve_recaptcha_v2(
                    site_key, page.url
                )
            elif "h-captcha" in content:
                captcha_type = "hCaptcha"
                self.stats.last_protection_event = "Solving hCaptcha..."
                self._notify_update()
                logging.info("Solving hCaptcha...")
                solution = await self._captcha_manager.solve_hcaptcha(
                    site_key, page.url
                )
            else:
                self.stats.captcha_pending -= 1
                return False

            self.stats.captcha_pending -= 1

            if solution.success and solution.token:
                self.stats.captcha_solved += 1
                self.stats.last_protection_event = f"{captcha_type} solved"
                self._notify_update()

                # Inject token
                await page.evaluate(
                    f"""
                    const textarea = document.querySelector('[name="g-recaptcha-response"], [name="h-captcha-response"]');
                    if (textarea) textarea.value = '{solution.token}';

                    // Trigger callback if exists
                    if (typeof ___grecaptcha_cfg !== 'undefined') {{
                        Object.keys(___grecaptcha_cfg.clients).forEach(key => {{
                            const client = ___grecaptcha_cfg.clients[key];
                            if (client.callback) client.callback('{solution.token}');
                        }});
                    }}
                """
                )

                await asyncio.sleep(1)
                return True
            else:
                self.stats.captcha_failed += 1
                self.stats.last_protection_event = (
                    f"{captcha_type} failed: {solution.error}"
                )
                self._notify_update()

        except Exception as e:
            self.stats.captcha_pending = max(0, self.stats.captcha_pending - 1)
            self.stats.captcha_failed += 1
            self.stats.last_protection_event = f"Captcha error: {str(e)[:30]}"
            logging.debug(f"Captcha handling error: {e}")

        return False

    async def _make_request(
        self, context: BrowserContext, proxy: ProxyConfig | None = None
    ):
        """
        Perform a single browser visit.

        Args:
            context: Browser context to use
            proxy: Proxy being used (for error tracking)
        """
        if not self.running:
            return

        page = None
        try:
            self.stats.active_threads += 1
            self.stats.total_requests += (
                1  # Increment at start so req >= success+failed always
            )

            page = await context.new_page()

            # Set referer
            referer = random.choice(get_referers())
            await page.set_extra_http_headers({"Referer": referer})

            # Navigate to target
            logging.debug(f"Navigating to {self.config.target_url}")
            response = await page.goto(
                self.config.target_url, wait_until="domcontentloaded", timeout=30000
            )

            success = False

            if response:
                status = response.status

                # Check for protection
                protection_type, site_key = await self._detect_protection(page)

                if protection_type == "cloudflare":
                    bypass_success = await self._handle_cloudflare(page, site_key)
                    if bypass_success:
                        # Verify we actually reached the target page with success status
                        # After bypass, the page should have navigated to actual content
                        try:
                            # Check current URL and verify it's not still a challenge
                            if await self._check_cloudflare_bypassed(page):
                                success = True
                            else:
                                logging.debug(
                                    "CF bypass reported success but page verification failed"
                                )
                                success = False
                        except Exception as e:
                            logging.debug(f"Post-bypass verification error: {e}")
                            success = False
                    else:
                        success = False
                elif protection_type == "captcha" and site_key:
                    success = await self._handle_captcha(page, site_key)
                elif protection_type == "akamai":
                    # Track Akamai detection
                    self.stats.akamai_detected += 1
                    self.stats.last_protection_event = "Akamai detected..."
                    self._notify_update()

                    # Akamai often resolves with JS execution - wait and check
                    await asyncio.sleep(2)
                    protection_type, _ = await self._detect_protection(page)
                    success = protection_type is None

                    if success:
                        self.stats.akamai_bypassed += 1
                        self.stats.last_protection_event = "Akamai bypassed"
                        self._notify_update()
                elif status in SUCCESS_STATUS_CODES:
                    success = True

                if success:
                    self.stats.success += 1
                    logging.debug(f"Success: {status}")
                else:
                    self.stats.failed += 1
                    logging.debug(
                        f"Failed: status={status}, protection={protection_type}"
                    )
            else:
                self.stats.failed += 1

            # Simulate reading time
            if self.running and success:
                view_time = random.uniform(
                    self.config.min_duration, self.config.max_duration
                )

                # Optional: simulate scrolling for more realism
                try:
                    await page.evaluate(
                        "window.scrollTo(0, document.body.scrollHeight / 2)"
                    )
                    await asyncio.sleep(view_time / 2)
                    await page.evaluate(
                        "window.scrollTo(0, document.body.scrollHeight)"
                    )
                    await asyncio.sleep(view_time / 2)
                except Exception:
                    await asyncio.sleep(view_time)

        except Exception as e:
            self.stats.failed += 1
            err_msg = str(e).lower()
            logging.debug(f"Browser request error: {err_msg}")

            # Expanded proxy error detection (includes SSL errors from MITM proxies)
            proxy_errors = [
                "err_proxy",
                "proxy_connection_failed",
                "err_tunnel",
                "err_connection_refused",
                "err_connection_timed_out",
                "err_connection_reset",
                "err_connection_closed",
                "err_socks_connection",
                "err_http_response_code_failure",
                "timeout",
                "net::err_",
                "ns_error_proxy",
                "proxyconnect",
                "could not connect",
                "connection refused",
                # SSL/TLS errors (often caused by MITM proxies)
                "err_cert_authority_invalid",
                "err_cert_common_name_invalid",
                "err_cert_date_invalid",
                "err_ssl_protocol_error",
                "err_ssl_version",
                "err_bad_ssl_client_auth_cert",
                "ssl_error",
                "certificate",
                "err_cert",
                # HTTP tunnel errors
                "tunnel failed",
                "response 400",
                "response 403",
                "response 407",
            ]
            is_proxy_error = proxy and any(err in err_msg for err in proxy_errors)

            if is_proxy_error:
                # Mark proxy for recycling - context will be recreated
                await self._mark_proxy_dead(proxy, context)

        finally:
            if page:
                with contextlib.suppress(Exception):
                    await page.close()

            self.stats.active_threads -= 1

            if self.on_update:
                self.stats.active_proxies = len(self.proxies)
                self.on_update(self.stats)

    async def run(self):
        """Main loop - spawn browser contexts and workers."""
        self.running = True
        self.stats = TrafficStats()

        # Re-initialize browser info in stats (stats was reset above)
        self.stats.browser_type = self._browser_name
        self.stats.contexts_total = self.config.browser.max_contexts

        self._log(f"Browser engine starting with {len(self.proxies)} proxies...")

        balance_task = None
        try:
            # Initialize captcha solver
            await self._init_captcha_solver()

            # Start balance check background task
            if self._captcha_manager:
                balance_task = asyncio.create_task(self._balance_check_loop())

            # Launch browser
            await self._launch_browser()

            # Determine number of contexts
            max_contexts = self.config.browser.max_contexts
            if self.proxies:
                max_contexts = min(max_contexts, len(self.proxies))
            max_contexts = max(1, max_contexts)

            # Create context pool with proxies
            self._log(f"Creating {max_contexts} browser contexts...")
            for i in range(max_contexts):
                proxy = self.proxies[i % len(self.proxies)] if self.proxies else None
                context, metadata = await self._create_context(proxy)
                self._contexts.append((context, proxy, metadata))

            self._log(f"Browser engine ready with {len(self._contexts)} contexts")

            tasks = set()
            context_index = 0
            no_proxy_warned = False

            while self.running:
                # Check if we've hit visit limit
                if (
                    self.config.total_visits > 0
                    and self.stats.total_requests >= self.config.total_visits
                ):
                    self.running = False
                    break

                # Handle case where all proxies/contexts have died
                if not self._contexts:
                    if not no_proxy_warned:
                        self._log(
                            "WARNING: All proxy contexts exhausted - creating direct connection fallback"
                        )
                        no_proxy_warned = True
                    # Create a single direct context (no proxy)
                    try:
                        direct_context, direct_meta = await self._create_context(
                            proxy=None
                        )
                        self._contexts.append((direct_context, None, direct_meta))
                        self._log("Direct connection context created")
                    except Exception as e:
                        self._log(f"Failed to create direct context: {e}")
                        self.running = False
                        break

                # Check for fingerprint rotation
                if self.config.browser.fingerprint_rotation_enabled:
                    await self._check_fingerprint_rotation()

                # Replenish tasks up to max contexts
                while (
                    len(tasks) < len(self._contexts) and self.running and self._contexts
                ):
                    if (
                        self.config.total_visits > 0
                        and self.stats.total_requests >= self.config.total_visits
                    ):
                        self.running = False
                        break

                    idx = context_index % len(self._contexts)
                    context, proxy, metadata = self._contexts[idx]
                    context_index += 1

                    # Increment request count for this context
                    metadata["request_count"] += 1

                    task = asyncio.create_task(self._make_request(context, proxy))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)

                if not self.running:
                    break

                # Slower polling for browser mode (more resource intensive)
                await asyncio.sleep(0.5)

            # Wait for pending tasks
            if tasks:
                self._log("Waiting for pending requests...")
                await asyncio.wait(tasks, timeout=15)

        except Exception as e:
            self._log(f"Browser engine error: {e}")

        finally:
            # Cancel balance check task
            if balance_task and not balance_task.done():
                balance_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await balance_task

            # Cleanup
            await self._cleanup()
            self._log(
                f"Browser engine stopped. {self.stats.success} success, {self.stats.failed} failed."
            )

    async def _cleanup(self):
        """Clean up browser resources."""
        # Save cookies from contexts before closing
        if self.session_manager and self._contexts:
            try:
                # Get cookies from the first active context
                context, _proxy, _meta = self._contexts[0]
                cookies = await context.cookies()
                if cookies:
                    self.session_manager.save_session(self._target_domain, cookies)
                    logging.debug(f"Saved {len(cookies)} cookies for {self._target_domain}")
            except Exception as e:
                logging.debug(f"Could not save session cookies: {e}")

        # Close contexts
        for context, _proxy, _meta in self._contexts:
            with contextlib.suppress(Exception):
                await context.close()
        self._contexts.clear()

        # Close browser
        if self._browser:
            with contextlib.suppress(Exception):
                await self._browser.close()
            self._browser = None

        # Stop playwright
        if self._playwright:
            with contextlib.suppress(Exception):
                await self._playwright.stop()
            self._playwright = None

    def stop(self):
        """Signal engine to stop."""
        self.running = False
        self._log("Browser engine stop requested")
