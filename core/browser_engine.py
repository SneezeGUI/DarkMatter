"""
Browser-based traffic engine using Playwright.
Provides realistic browser automation with protection bypass capabilities.
Matches AsyncTrafficEngine interface for UI compatibility.
Supports Chrome, Edge, Brave (Chromium) and Firefox browsers.
"""
import asyncio
import random
import logging
from typing import List, Callable, Optional, Any
from .models import TrafficConfig, ProxyConfig, TrafficStats, CaptchaProvider
from .browser_manager import BrowserManager
from .constants import (
    DEFAULT_REFERERS,
    CLOUDFLARE_MARKERS,
    CAPTCHA_MARKERS,
    AKAMAI_MARKERS,
    BROWSER_USER_AGENTS,
    BROWSER_VIEWPORTS,
    SUCCESS_STATUS_CODES,
)

# Playwright imports are done lazily to avoid import errors if not installed
playwright_available = False
try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
    playwright_available = True
except ImportError:
    pass


# Stealth script for Chromium-based browsers (Chrome, Edge, Brave)
CHROMIUM_STEALTH_SCRIPT = """
// Remove webdriver flag
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Add Chrome object
window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {}
};

// Fix permissions query
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);

// Fake plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5]
});

// Fake languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en']
});

// Hide automation
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;

// WebGL vendor/renderer spoofing
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.apply(this, arguments);
};
"""

# Stealth script for Firefox (different detection methods)
FIREFOX_STEALTH_SCRIPT = """
// Remove webdriver flag
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Fix permissions query
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);

// Fake plugins (Firefox style)
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        return {
            length: 5,
            item: (i) => null,
            namedItem: (n) => null,
            refresh: () => {}
        };
    }
});

// Fake languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en']
});

// WebGL vendor/renderer spoofing for Firefox
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.apply(this, arguments);
};
"""


class PlaywrightTrafficEngine:
    """
    Browser-based traffic engine with Cloudflare/Akamai bypass.
    Uses Playwright for realistic browser automation.
    """

    @staticmethod
    def _filter_browser_proxies(proxies: List[ProxyConfig]) -> List[ProxyConfig]:
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
        https_capable_ports = {8080, 3128, 8888, 8118, 8000, 8008, 8081, 9080, 1080, 443}

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
            logging.info(f"Browser mode: Skipped {len(skipped)} port-80 HTTP proxies (can't tunnel HTTPS)")

        # Return prioritized list
        result = socks5 + socks4 + http_proxy_ports + http_other

        if result:
            logging.info(f"Browser mode: Using {len(result)} compatible proxies "
                        f"(SOCKS5: {len(socks5)}, SOCKS4: {len(socks4)}, HTTP: {len(http_proxy_ports) + len(http_other)})")
        else:
            logging.warning("Browser mode: No browser-compatible proxies found!")

        return result

    def __init__(
        self,
        config: TrafficConfig,
        proxies: List[ProxyConfig],
        on_update: Optional[Callable[[TrafficStats], None]] = None
    ):
        """
        Initialize the browser engine.

        Args:
            config: Traffic configuration including browser settings
            proxies: List of proxy configurations
            on_update: Callback for stats updates
        """
        if not playwright_available:
            raise ImportError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            )

        self.config = config
        self.proxies = self._filter_browser_proxies(list(proxies))  # Filter and copy
        self.on_update = on_update
        self.stats = TrafficStats()
        self.running = False
        self._initial_proxy_count = len(proxies)
        self._filtered_proxy_count = len(self.proxies)

        # Get browser executable path from config
        self._executable_path = config.browser.get_executable_path()

        # Determine browser type from configured path
        self._browser_type = BrowserManager.get_browser_type_from_path(
            self._executable_path or ""
        )

        # Get browser name for display
        browser_info = BrowserManager.get_browser_info_from_path(self._executable_path or "")
        self._browser_name = browser_info.name if browser_info else ("Firefox" if self._browser_type == "firefox" else "Chromium")

        # Playwright objects
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._contexts: List[BrowserContext] = []

        # Captcha manager (lazy loaded)
        self._captcha_manager = None

        # Initialize browser info in stats
        self.stats.browser_type = self._browser_name
        self.stats.contexts_total = config.browser.max_contexts

    async def _init_captcha_solver(self):
        """Initialize captcha manager if any provider is configured."""
        if self.config.captcha.has_any_provider():
            try:
                from .captcha_manager import create_captcha_manager
                self._captcha_manager = create_captcha_manager(self.config.captcha)
                if self._captcha_manager:
                    providers = self._captcha_manager.get_available_providers()
                    logging.info(f"Captcha manager initialized with providers: {providers}")
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
                logging.info("Firefox browser launched successfully")
            else:
                # Chromium covers Chrome, Edge, and Brave
                self._browser = await self._playwright.chromium.launch(**launch_options)
                logging.info("Chromium-based browser launched successfully")
        except Exception as e:
            logging.error(f"Failed to launch browser: {e}")
            raise

    async def _create_context(self, proxy: Optional[ProxyConfig] = None) -> BrowserContext:
        """
        Create a browser context with realistic fingerprint.

        Args:
            proxy: Optional proxy configuration for this context

        Returns:
            Configured BrowserContext
        """
        # Random viewport for variety
        viewport = random.choice(BROWSER_VIEWPORTS)
        user_agent = random.choice(BROWSER_USER_AGENTS)

        context_options = {
            "viewport": {
                "width": viewport[0],
                "height": viewport[1]
            },
            "user_agent": user_agent,
            "locale": self.config.browser.locale,
            "timezone_id": self.config.browser.timezone,
            "ignore_https_errors": not self.config.verify_ssl,
        }

        # Configure proxy if provided
        if proxy:
            proxy_url = f"{proxy.protocol}://{proxy.host}:{proxy.port}"
            context_options["proxy"] = {"server": proxy_url}

            if proxy.username and proxy.password:
                context_options["proxy"]["username"] = proxy.username
                context_options["proxy"]["password"] = proxy.password

        context = await self._browser.new_context(**context_options)

        # Apply stealth scripts if enabled (use browser-appropriate script)
        if self.config.browser.stealth_enabled:
            stealth_script = FIREFOX_STEALTH_SCRIPT if self._browser_type == "firefox" else CHROMIUM_STEALTH_SCRIPT
            await context.add_init_script(stealth_script)

        return context

    async def _detect_protection(self, page: Page) -> tuple:
        """
        Detect if page has bot protection.

        Args:
            page: Playwright page object

        Returns:
            Tuple of (protection_type, site_key)
            protection_type: "cloudflare", "akamai", "captcha", or None
            site_key: Captcha site key if found, else None
        """
        try:
            content = await page.content()

            # Check Cloudflare
            for marker in CLOUDFLARE_MARKERS:
                if marker in content:
                    site_key = await self._extract_site_key(page, "turnstile")
                    return "cloudflare", site_key

            # Check Akamai
            for marker in AKAMAI_MARKERS:
                if marker in content:
                    return "akamai", None

            # Check generic captcha
            for marker in CAPTCHA_MARKERS:
                if marker in content:
                    site_key = await self._extract_site_key(page, "recaptcha")
                    if not site_key:
                        site_key = await self._extract_site_key(page, "hcaptcha")
                    return "captcha", site_key

        except Exception as e:
            logging.debug(f"Protection detection error: {e}")

        return None, None

    async def _extract_site_key(self, page: Page, captcha_type: str) -> Optional[str]:
        """Extract captcha site key from page."""
        try:
            selectors = {
                "turnstile": "[data-sitekey], .cf-turnstile[data-sitekey]",
                "recaptcha": ".g-recaptcha[data-sitekey], [data-sitekey]",
                "hcaptcha": ".h-captcha[data-sitekey], [data-sitekey]",
            }

            selector = selectors.get(captcha_type, "[data-sitekey]")
            element = await page.query_selector(selector)

            if element:
                return await element.get_attribute("data-sitekey")

        except Exception as e:
            logging.debug(f"Site key extraction error: {e}")

        return None

    async def _handle_cloudflare(self, page: Page, site_key: Optional[str]) -> bool:
        """
        Handle Cloudflare challenge.

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

        logging.info("Cloudflare challenge detected, waiting...")

        try:
            # Wait for challenge to auto-resolve
            wait_ms = self.config.protection.cloudflare_wait_seconds * 1000
            await page.wait_for_load_state("networkidle", timeout=wait_ms)

            # Check if resolved
            protection_type, _ = await self._detect_protection(page)
            if protection_type is None:
                logging.info("Cloudflare challenge auto-resolved")
                self.stats.cloudflare_bypassed += 1
                self.stats.last_protection_event = "Cloudflare auto-bypassed"
                self._notify_update()
                return True

            # Try captcha manager if available and configured
            if site_key and self._captcha_manager and self.config.protection.auto_solve_captcha:
                self.stats.last_protection_event = "Solving Turnstile..."
                self.stats.captcha_pending += 1
                self._notify_update()

                logging.info("Attempting Turnstile solve...")
                solution = await self._captcha_manager.solve_turnstile(site_key, page.url)

                self.stats.captcha_pending -= 1

                if solution.success and solution.token:
                    self.stats.captcha_solved += 1

                    # Inject solution
                    await page.evaluate(f"""
                        const input = document.querySelector('[name="cf-turnstile-response"]');
                        if (input) input.value = '{solution.token}';

                        // Try to submit
                        const form = document.querySelector('form');
                        if (form) form.submit();
                    """)

                    await asyncio.sleep(2)
                    await page.wait_for_load_state("networkidle", timeout=10000)

                    # Verify
                    protection_type, _ = await self._detect_protection(page)
                    if protection_type is None:
                        logging.info("Cloudflare bypass successful via captcha solve")
                        self.stats.cloudflare_bypassed += 1
                        self.stats.last_protection_event = "Cloudflare bypassed (captcha)"
                        self._notify_update()
                        return True
                else:
                    self.stats.captcha_failed += 1
                    self.stats.last_protection_event = f"Captcha failed: {solution.error}"

                self._notify_update()

        except Exception as e:
            logging.debug(f"Cloudflare handling error: {e}")
            self.stats.last_protection_event = f"Cloudflare error: {str(e)[:30]}"

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
                logging.warning(f"Removed dead proxy {proxy.host}:{proxy.port}")
            except ValueError:
                pass

        # Find and remove the context from our pool
        for i, (ctx, ctx_proxy) in enumerate(self._contexts):
            if ctx_proxy == proxy:
                try:
                    await ctx.close()
                except Exception:
                    pass
                self._contexts.pop(i)
                logging.debug(f"Closed context for dead proxy {proxy.host}:{proxy.port}")
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
            for _, ctx_proxy in self._contexts
            if ctx_proxy is not None
        }
        available = [
            p for p in self.proxies
            if (p.host, p.port) not in used_proxy_keys
        ]

        if not available:
            # All proxies in use, just pick any
            available = self.proxies

        if available:
            proxy = random.choice(available)
            try:
                context = await self._create_context(proxy)
                self._contexts.append((context, proxy))
                logging.info(f"Recycled context with proxy {proxy.host}:{proxy.port}")
            except Exception as e:
                logging.debug(f"Failed to recycle context: {e}")

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
                solution = await self._captcha_manager.solve_recaptcha_v2(site_key, page.url)
            elif "h-captcha" in content:
                captcha_type = "hCaptcha"
                self.stats.last_protection_event = "Solving hCaptcha..."
                self._notify_update()
                logging.info("Solving hCaptcha...")
                solution = await self._captcha_manager.solve_hcaptcha(site_key, page.url)
            else:
                self.stats.captcha_pending -= 1
                return False

            self.stats.captcha_pending -= 1

            if solution.success and solution.token:
                self.stats.captcha_solved += 1
                self.stats.last_protection_event = f"{captcha_type} solved"
                self._notify_update()

                # Inject token
                await page.evaluate(f"""
                    const textarea = document.querySelector('[name="g-recaptcha-response"], [name="h-captcha-response"]');
                    if (textarea) textarea.value = '{solution.token}';

                    // Trigger callback if exists
                    if (typeof ___grecaptcha_cfg !== 'undefined') {{
                        Object.keys(___grecaptcha_cfg.clients).forEach(key => {{
                            const client = ___grecaptcha_cfg.clients[key];
                            if (client.callback) client.callback('{solution.token}');
                        }});
                    }}
                """)

                await asyncio.sleep(1)
                return True
            else:
                self.stats.captcha_failed += 1
                self.stats.last_protection_event = f"{captcha_type} failed: {solution.error}"
                self._notify_update()

        except Exception as e:
            self.stats.captcha_pending = max(0, self.stats.captcha_pending - 1)
            self.stats.captcha_failed += 1
            self.stats.last_protection_event = f"Captcha error: {str(e)[:30]}"
            logging.debug(f"Captcha handling error: {e}")

        return False

    async def _make_request(self, context: BrowserContext, proxy: Optional[ProxyConfig] = None):
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
            if self.on_update:
                self.stats.active_proxies = len(self.proxies)
                self.on_update(self.stats)

            page = await context.new_page()

            # Set referer
            referer = random.choice(DEFAULT_REFERERS)
            await page.set_extra_http_headers({"Referer": referer})

            # Navigate to target
            logging.debug(f"Navigating to {self.config.target_url}")
            response = await page.goto(
                self.config.target_url,
                wait_until="domcontentloaded",
                timeout=30000
            )

            success = False

            if response:
                status = response.status

                # Check for protection
                protection_type, site_key = await self._detect_protection(page)

                if protection_type == "cloudflare":
                    success = await self._handle_cloudflare(page, site_key)
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
                    logging.debug(f"Failed: {status}, protection: {protection_type}")
            else:
                self.stats.failed += 1

            # Simulate reading time
            if self.running and success:
                view_time = random.uniform(self.config.min_duration, self.config.max_duration)

                # Optional: simulate scrolling for more realism
                try:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                    await asyncio.sleep(view_time / 2)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(view_time / 2)
                except Exception:
                    await asyncio.sleep(view_time)

        except Exception as e:
            self.stats.failed += 1
            err_msg = str(e).lower()
            logging.debug(f"Browser request error: {err_msg}")

            # Expanded proxy error detection (includes SSL errors from MITM proxies)
            proxy_errors = [
                "err_proxy", "proxy_connection_failed", "err_tunnel",
                "err_connection_refused", "err_connection_timed_out",
                "err_connection_reset", "err_connection_closed",
                "err_socks_connection", "err_http_response_code_failure",
                "timeout", "net::err_", "ns_error_proxy",
                "proxyconnect", "could not connect", "connection refused",
                # SSL/TLS errors (often caused by MITM proxies)
                "err_cert_authority_invalid", "err_cert_common_name_invalid",
                "err_cert_date_invalid", "err_ssl_protocol_error",
                "err_ssl_version", "err_bad_ssl_client_auth_cert",
                "ssl_error", "certificate", "err_cert",
                # HTTP tunnel errors
                "tunnel failed", "response 400", "response 403", "response 407"
            ]
            is_proxy_error = proxy and any(err in err_msg for err in proxy_errors)

            if is_proxy_error:
                # Mark proxy for recycling - context will be recreated
                await self._mark_proxy_dead(proxy, context)

        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass

            self.stats.active_threads -= 1
            self.stats.total_requests += 1

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

        logging.info("Browser engine starting...")

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
            logging.info(f"Creating {max_contexts} browser contexts...")
            for i in range(max_contexts):
                proxy = self.proxies[i % len(self.proxies)] if self.proxies else None
                context = await self._create_context(proxy)
                self._contexts.append((context, proxy))

            logging.info(f"Browser engine ready with {len(self._contexts)} contexts")

            tasks = set()
            context_index = 0
            no_proxy_warned = False

            while self.running:
                # Check if we've hit visit limit
                if self.config.total_visits > 0 and self.stats.total_requests >= self.config.total_visits:
                    self.running = False
                    break

                # Handle case where all proxies/contexts have died
                if not self._contexts:
                    if not no_proxy_warned:
                        logging.warning("All proxy contexts exhausted - creating direct connection fallback")
                        no_proxy_warned = True
                    # Create a single direct context (no proxy)
                    try:
                        direct_context = await self._create_context(proxy=None)
                        self._contexts.append((direct_context, None))
                        logging.info("Direct connection context created")
                    except Exception as e:
                        logging.error(f"Failed to create direct context: {e}")
                        self.running = False
                        break

                # Replenish tasks up to max contexts
                while len(tasks) < len(self._contexts) and self.running and self._contexts:
                    if self.config.total_visits > 0 and self.stats.total_requests >= self.config.total_visits:
                        self.running = False
                        break

                    context, proxy = self._contexts[context_index % len(self._contexts)]
                    context_index += 1

                    task = asyncio.create_task(self._make_request(context, proxy))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)

                if not self.running:
                    break

                # Slower polling for browser mode (more resource intensive)
                await asyncio.sleep(0.5)

            # Wait for pending tasks
            if tasks:
                logging.info("Waiting for pending requests...")
                await asyncio.wait(tasks, timeout=15)

        except Exception as e:
            logging.error(f"Browser engine error: {e}")

        finally:
            # Cancel balance check task
            if balance_task and not balance_task.done():
                balance_task.cancel()
                try:
                    await balance_task
                except asyncio.CancelledError:
                    pass

            # Cleanup
            await self._cleanup()
            logging.info("Browser engine stopped")

    async def _cleanup(self):
        """Clean up browser resources."""
        # Close contexts
        for context, _ in self._contexts:
            try:
                await context.close()
            except Exception:
                pass
        self._contexts.clear()

        # Close browser
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        # Stop playwright
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def stop(self):
        """Signal engine to stop."""
        self.running = False
        logging.info("Browser engine stop requested")
