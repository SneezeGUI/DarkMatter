from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class EngineMode(Enum):
    """Traffic engine mode selection."""
    CURL = "curl"        # Fast, curl_cffi-based
    BROWSER = "browser"  # Realistic, Playwright-based


class CaptchaProvider(Enum):
    """Supported captcha solving providers."""
    NONE = "none"
    TWOCAPTCHA = "2captcha"
    ANTICAPTCHA = "anticaptcha"
    AUTO = "auto"  # Automatically select based on availability


class CaptchaType(Enum):
    """Types of captchas that can be solved."""
    TURNSTILE = "turnstile"       # Cloudflare Turnstile
    RECAPTCHA_V2 = "recaptcha_v2"  # Google reCAPTCHA v2
    RECAPTCHA_V3 = "recaptcha_v3"  # Google reCAPTCHA v3
    HCAPTCHA = "hcaptcha"          # hCaptcha


class BrowserSelection(Enum):
    """Browser selection options."""
    AUTO = "auto"      # Auto-detect best available
    CHROME = "chrome"
    CHROMIUM = "chromium"  # Open-source Chromium (including Playwright bundled)
    EDGE = "edge"
    BRAVE = "brave"
    FIREFOX = "firefox"
    OTHER = "other"    # Custom path

@dataclass
class ProxyConfig:
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: str = "http"  # http, socks5
    score: float = 0.0

    def to_curl_cffi_format(self) -> str:
        """Returns proxy string formatted for curl_cffi."""
        auth = f"{self.username}:{self.password}@" if self.username and self.password else ""
        return f"{self.protocol}://{auth}{self.host}:{self.port}"

@dataclass
class BrowserConfig:
    """Configuration for browser-based traffic generation."""
    # Browser selection and paths
    selected_browser: BrowserSelection = BrowserSelection.AUTO
    chrome_path: str = ""
    chromium_path: str = ""  # Open-source Chromium / Playwright bundled
    edge_path: str = ""
    brave_path: str = ""
    firefox_path: str = ""
    other_path: str = ""
    # Runtime settings
    headless: bool = True
    max_contexts: int = 5  # Concurrent browser contexts (RAM-limited)
    viewport_width: int = 1920
    viewport_height: int = 1080
    locale: str = "en-US"
    timezone: str = "America/New_York"
    stealth_enabled: bool = True  # Anti-detection scripts

    def get_executable_path(self) -> Optional[str]:
        """Get the executable path based on selection."""
        if self.selected_browser == BrowserSelection.CHROME and self.chrome_path:
            return self.chrome_path
        elif self.selected_browser == BrowserSelection.CHROMIUM and self.chromium_path:
            return self.chromium_path
        elif self.selected_browser == BrowserSelection.EDGE and self.edge_path:
            return self.edge_path
        elif self.selected_browser == BrowserSelection.BRAVE and self.brave_path:
            return self.brave_path
        elif self.selected_browser == BrowserSelection.FIREFOX and self.firefox_path:
            return self.firefox_path
        elif self.selected_browser == BrowserSelection.OTHER and self.other_path:
            return self.other_path
        # AUTO or no path set - return None for auto-detection
        return None


@dataclass
class CaptchaConfig:
    """Configuration for captcha solving services with multi-provider support."""
    # API keys for each provider
    twocaptcha_key: str = ""
    anticaptcha_key: str = ""
    # Provider selection
    primary_provider: CaptchaProvider = CaptchaProvider.AUTO
    fallback_enabled: bool = True  # Try other provider if primary fails
    timeout_seconds: int = 120  # Max wait for solution

    def get_available_providers(self) -> list:
        """Return list of providers that have API keys configured."""
        available = []
        if self.twocaptcha_key:
            available.append(CaptchaProvider.TWOCAPTCHA)
        if self.anticaptcha_key:
            available.append(CaptchaProvider.ANTICAPTCHA)
        return available

    def has_any_provider(self) -> bool:
        """Check if any captcha provider is configured."""
        return bool(self.twocaptcha_key or self.anticaptcha_key)


@dataclass
class ProtectionBypassConfig:
    """Settings for bypassing bot protection systems."""
    cloudflare_enabled: bool = True
    cloudflare_wait_seconds: int = 10  # Wait for JS challenge
    akamai_enabled: bool = True
    auto_solve_captcha: bool = True  # Auto-trigger solver on detection


@dataclass
class TrafficConfig:
    """Configuration for traffic generation."""
    target_url: str
    max_threads: int
    total_visits: int
    min_duration: int  # Seconds
    max_duration: int  # Seconds
    headless: bool = True
    verify_ssl: bool = True
    # New fields for browser mode
    engine_mode: EngineMode = EngineMode.CURL
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    captcha: CaptchaConfig = field(default_factory=CaptchaConfig)
    protection: ProtectionBypassConfig = field(default_factory=ProtectionBypassConfig)

@dataclass
class TrafficStats:
    """Traffic generation statistics with browser and captcha tracking."""
    # Core stats
    success: int = 0
    failed: int = 0
    active_threads: int = 0
    total_requests: int = 0
    active_proxies: int = 0

    # Browser stats (browser mode only)
    browser_type: str = ""  # "Chrome", "Edge", "Brave", "Firefox", ""
    active_contexts: int = 0
    contexts_total: int = 0

    # Captcha stats
    captcha_solved: int = 0
    captcha_failed: int = 0
    captcha_pending: int = 0
    captcha_balance_2captcha: float = -1  # -1 = not checked
    captcha_balance_anticaptcha: float = -1

    # Protection detection stats
    cloudflare_detected: int = 0
    cloudflare_bypassed: int = 0
    akamai_detected: int = 0
    akamai_bypassed: int = 0
    captcha_detected: int = 0  # Generic captcha pages

    # Last protection event for display
    last_protection_event: str = ""  # e.g., "Cloudflare bypassed", "Solving captcha..."

@dataclass
class ProxyCheckResult:
    proxy: ProxyConfig
    status: str  # "Active" or "Dead"
    speed: int  # ms
    type: str  # HTTP, SOCKS5, etc.
    country: str
    country_code: str
    city: str = ""
    anonymity: str = "Unknown"  # "Elite", "Anonymous", "Transparent"
    score: float = 0.0
    bytes_transferred: int = 0  # Total bytes (request + response + TLS overhead)

