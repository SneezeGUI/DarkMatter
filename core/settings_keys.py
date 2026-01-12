"""
Settings key constants for DarkMatter Traffic Bot.

This module provides type-safe access to settings keys and their defaults,
eliminating magic strings throughout the codebase.

Usage:
    from core.settings_keys import SettingsKeys, Defaults

    # Access key name
    key = SettingsKeys.ENGINE_MODE  # "engine_mode"

    # Access default value
    default = Defaults.ENGINE_MODE  # "curl"

    # Use in settings access
    mode = settings.get(SettingsKeys.ENGINE_MODE, Defaults.ENGINE_MODE)
"""



class SettingsKeys:
    """
    Defines string constants for all application settings keys.
    Used to avoid magic strings when accessing the configuration dictionary.
    """

    # --- Traffic Settings ---
    TARGET_URL = "target_url"
    THREADS = "threads"
    VIEWTIME_MIN = "viewtime_min"
    VIEWTIME_MAX = "viewtime_max"
    ENGINE_MODE = "engine_mode"
    BURST_MODE = "burst_mode"
    BURST_REQUESTS = "burst_requests"
    BURST_SLEEP_MIN = "burst_sleep_min"
    BURST_SLEEP_MAX = "burst_sleep_max"
    VERIFY_SSL = "verify_ssl"

    # --- Browser Settings ---
    HEADLESS = "headless"
    BROWSER_SELECTED = "browser_selected"
    BROWSER_CHROME_PATH = "browser_chrome_path"
    BROWSER_CHROMIUM_PATH = "browser_chromium_path"
    BROWSER_EDGE_PATH = "browser_edge_path"
    BROWSER_BRAVE_PATH = "browser_brave_path"
    BROWSER_FIREFOX_PATH = "browser_firefox_path"
    BROWSER_OTHER_PATH = "browser_other_path"
    BROWSER_CONTEXTS = "browser_contexts"
    BROWSER_STEALTH = "browser_stealth"
    BROWSER_LOCALE = "browser_locale"
    BROWSER_TIMEZONE = "browser_timezone"

    # --- Captcha Settings ---
    CAPTCHA_PRIMARY = "captcha_primary"
    CAPTCHA_2CAPTCHA_KEY = "captcha_2captcha_key"
    CAPTCHA_ANTICAPTCHA_KEY = "captcha_anticaptcha_key"
    CAPTCHA_FALLBACK_ENABLED = "captcha_fallback_enabled"
    CAPTCHA_TIMEOUT = "captcha_timeout"
    CLOUDFLARE_BYPASS = "cloudflare_bypass"
    AKAMAI_BYPASS = "akamai_bypass"
    AUTO_SOLVE_CAPTCHA = "auto_solve_captcha"
    CLOUDFLARE_WAIT = "cloudflare_wait"

    # --- Proxy Settings ---
    SOURCES = "sources"
    PROXY_TEST_URL = "proxy_test_url"
    PROXY_TIMEOUT = "proxy_timeout"
    PROXY_CHECK_THREADS = "proxy_check_threads"
    PROXY_SCRAPE_THREADS = "proxy_scrape_threads"
    USE_HTTP = "use_http"
    USE_SOCKS4 = "use_socks4"
    USE_SOCKS5 = "use_socks5"
    HIDE_DEAD = "hide_dead"
    SYSTEM_PROXY = "system_proxy"
    SYSTEM_PROXY_PROTOCOL = "system_proxy_protocol"
    USE_PROXY_FOR_SCRAPE = "use_proxy_for_scrape"
    USE_PROXY_FOR_CHECK = "use_proxy_for_check"
    USE_MANUAL_TARGET = "use_manual_target"
    VALIDATORS_ENABLED = "validators_enabled"
    VALIDATOR_TEST_DEPTH = "validator_test_depth"

    # --- Master/Slave Settings ---
    MODE = "mode"
    CONNECTION_MODE = "connection_mode"
    MASTER_HOST = "master_host"
    MASTER_PORT = "master_port"
    MASTER_SECRET_KEY = "master_secret_key"
    SLAVE_SECRET_KEY = "slave_secret_key"
    SLAVE_NAME = "slave_name"
    RELAY_URL = "relay_url"

    # --- UI/Export Settings ---
    EXPORT_FOLDER = "export_folder"
    EXPORT_WITH_PROTOCOL = "export_with_protocol"


class Defaults:
    """
    Defines default values for all application settings.
    Used when initializing configuration or resetting to defaults.
    """

    # --- Traffic Defaults ---
    TARGET_URL: str = ""
    THREADS: int = 10
    VIEWTIME_MIN: int = 5
    VIEWTIME_MAX: int = 30
    ENGINE_MODE: str = "curl"  # "curl" or "browser"
    BURST_MODE: bool = False
    BURST_REQUESTS: int = 10
    BURST_SLEEP_MIN: int = 2
    BURST_SLEEP_MAX: int = 5
    VERIFY_SSL: bool = True

    # --- Browser Defaults ---
    HEADLESS: bool = True
    BROWSER_SELECTED: str = "auto"
    BROWSER_CHROME_PATH: str = ""
    BROWSER_CHROMIUM_PATH: str = ""
    BROWSER_EDGE_PATH: str = ""
    BROWSER_BRAVE_PATH: str = ""
    BROWSER_FIREFOX_PATH: str = ""
    BROWSER_OTHER_PATH: str = ""
    BROWSER_CONTEXTS: int = 3
    BROWSER_STEALTH: bool = True
    BROWSER_LOCALE: str = "en-US"
    BROWSER_TIMEZONE: str = "America/New_York"

    # --- Captcha Defaults ---
    CAPTCHA_PRIMARY: str = "auto"
    CAPTCHA_2CAPTCHA_KEY: str = ""
    CAPTCHA_ANTICAPTCHA_KEY: str = ""
    CAPTCHA_FALLBACK_ENABLED: bool = True
    CAPTCHA_TIMEOUT: int = 120
    CLOUDFLARE_BYPASS: bool = True
    AKAMAI_BYPASS: bool = True
    AUTO_SOLVE_CAPTCHA: bool = False
    CLOUDFLARE_WAIT: int = 15

    # --- Proxy Defaults ---
    SOURCES: str = "resources/sources.txt"
    PROXY_TEST_URL: str = "https://www.google.com"
    PROXY_TIMEOUT: int = 5000
    PROXY_CHECK_THREADS: int = 500
    PROXY_SCRAPE_THREADS: int = 50
    USE_HTTP: bool = True
    USE_SOCKS4: bool = True
    USE_SOCKS5: bool = True
    HIDE_DEAD: bool = False
    SYSTEM_PROXY: str = ""
    SYSTEM_PROXY_PROTOCOL: str = "http"
    USE_PROXY_FOR_SCRAPE: bool = False
    USE_PROXY_FOR_CHECK: bool = False
    USE_MANUAL_TARGET: bool = False
    VALIDATORS_ENABLED: dict[str, bool] = {}
    VALIDATOR_TEST_DEPTH: str = "normal"

    # --- Master/Slave Defaults ---
    MODE: str = "standalone"
    CONNECTION_MODE: str = "direct"
    MASTER_HOST: str = "127.0.0.1"
    MASTER_PORT: int = 8765
    MASTER_SECRET_KEY: str = ""
    SLAVE_SECRET_KEY: str = ""
    SLAVE_NAME: str = "slave-01"
    RELAY_URL: str = ""

    # --- UI/Export Defaults ---
    EXPORT_FOLDER: str = ""
    EXPORT_WITH_PROTOCOL: bool = True
