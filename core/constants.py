"""
Application-wide constants and configuration defaults.
"""

# Browser impersonation options for TLS fingerprinting
BROWSER_IMPERSONATIONS = ["chrome120", "chrome124", "safari15_5"]

# Proxy checking defaults
DEFAULT_PROXY_TIMEOUT_MS = 3000
MIN_PROXY_TIMEOUT_MS = 100
MAX_PROXY_TIMEOUT_MS = 30000

DEFAULT_CHECK_THREADS = 50
MIN_CHECK_THREADS = 1
MAX_CHECK_THREADS = 2000

DEFAULT_SCRAPE_THREADS = 20
MIN_SCRAPE_THREADS = 1
MAX_SCRAPE_THREADS = 100

# Traffic engine defaults
DEFAULT_ATTACK_THREADS = 5
MIN_ATTACK_THREADS = 1
MAX_ATTACK_THREADS = 500

DEFAULT_VIEW_TIME_MIN = 5
DEFAULT_VIEW_TIME_MAX = 10
MIN_VIEW_TIME = 1
MAX_VIEW_TIME = 300

# Request defaults
REQUEST_TIMEOUT_SECONDS = 30
SCRAPE_TIMEOUT_SECONDS = 15

# Proxy checker batch size (for staggered launch)
PROXY_CHECK_BATCH_SIZE = 50

# GUI update interval (ms)
GUI_UPDATE_INTERVAL_MS = 100

# Buffer drain limit per GUI update
BUFFER_DRAIN_LIMIT = 40

# Curl error codes indicating proxy failure
PROXY_ERROR_CODES = ["curl: (56)", "curl: (97)", "curl: (28)", "curl: (7)", "curl: (35)"]

# Success status codes
SUCCESS_STATUS_CODES = [200, 201, 301, 302]

# Dead proxy sentinel speed value
DEAD_PROXY_SPEED_MS = 9999

# Browser-consistent headers for use with curl_cffi impersonation
# Note: User-Agent is NOT included - curl_cffi sets it automatically based on impersonate value
BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "max-age=0",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# Common referer sources for traffic diversity
DEFAULT_REFERERS = [
    "https://www.google.com/",
    "https://www.bing.com/",
    "https://duckduckgo.com/",
    "https://www.google.co.uk/",
    "https://search.yahoo.com/",
]

# =============================================================================
# Browser Engine Constants (Playwright-based)
# =============================================================================

# Browser context limits (RAM-constrained)
DEFAULT_BROWSER_CONTEXTS = 5
MIN_BROWSER_CONTEXTS = 1
MAX_BROWSER_CONTEXTS = 10

# Protection bypass timing
CLOUDFLARE_WAIT_SECONDS = 10
CAPTCHA_TIMEOUT_SECONDS = 120

# Common browser viewports for realistic traffic
BROWSER_VIEWPORTS = [
    (1920, 1080),  # Full HD (most common)
    (1366, 768),   # HD laptop
    (1536, 864),   # Surface/laptop scaled
    (1440, 900),   # MacBook
    (2560, 1440),  # QHD monitor
]

# Cloudflare detection markers in page content
CLOUDFLARE_MARKERS = [
    "cf-browser-verification",
    "challenge-platform",
    "__cf_chl_opt",
    "Checking your browser",
    "cf_chl_prog",
    "Just a moment...",
    "Enable JavaScript and cookies",
]

# Captcha detection markers
CAPTCHA_MARKERS = [
    "g-recaptcha",
    "cf-turnstile",
    "h-captcha",
    "data-sitekey",
    "grecaptcha",
]

# Akamai Bot Manager detection markers
AKAMAI_MARKERS = [
    "_abck",
    "bm_sz",
    "ak_bmsc",
    "akamai",
]

# Browser error patterns
BROWSER_ERROR_PATTERNS = [
    "net::ERR_",
    "Timeout",
    "Navigation failed",
    "Target closed",
    "Protocol error",
]

# User agents for browser mode (matched to viewport for consistency)
BROWSER_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]
