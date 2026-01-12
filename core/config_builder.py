"""
Traffic configuration builder for DarkMatter Traffic Bot.

This module provides a builder pattern for assembling TrafficConfig objects
from settings dictionaries, centralizing all the mapping and conversion logic.
"""

from typing import Any

from core.models import (
    BrowserConfig,
    BrowserSelection,
    CaptchaConfig,
    CaptchaProvider,
    EngineMode,
    ProtectionBypassConfig,
    TrafficConfig,
)
from core.settings_keys import Defaults, SettingsKeys


class TrafficConfigBuilder:
    """
    Builder class responsible for creating TrafficConfig objects from raw settings dictionaries.
    Handles type conversions, enum mappings, and default value application.
    """

    BROWSER_SELECTION_MAP = {
        "auto": BrowserSelection.AUTO,
        "chrome": BrowserSelection.CHROME,
        "chromium": BrowserSelection.CHROMIUM,
        "edge": BrowserSelection.EDGE,
        "brave": BrowserSelection.BRAVE,
        "firefox": BrowserSelection.FIREFOX,
        "other": BrowserSelection.OTHER,
    }

    CAPTCHA_PROVIDER_MAP = {
        "auto": CaptchaProvider.AUTO,
        "2captcha": CaptchaProvider.TWOCAPTCHA,
        "anticaptcha": CaptchaProvider.ANTICAPTCHA,
        "none": CaptchaProvider.NONE,
    }

    @staticmethod
    def from_settings(settings: dict[str, Any], target_url: str) -> TrafficConfig:
        """
        Creates a fully populated TrafficConfig object from a settings dictionary.

        Args:
            settings: Dictionary containing application settings (keys from SettingsKeys).
            target_url: The target URL for traffic generation.

        Returns:
            A TrafficConfig object ready for use by the traffic engine.
        """
        # Determine engine mode
        mode_str = settings.get(SettingsKeys.ENGINE_MODE, Defaults.ENGINE_MODE)
        engine_mode = (
            EngineMode.BROWSER if mode_str == "browser" else EngineMode.CURL
        )

        return TrafficConfig(
            target_url=target_url,
            max_threads=int(settings.get(SettingsKeys.THREADS, Defaults.THREADS)),
            total_visits=0,  # Infinite run until stopped usually
            min_duration=int(settings.get(SettingsKeys.VIEWTIME_MIN, Defaults.VIEWTIME_MIN)),
            max_duration=int(settings.get(SettingsKeys.VIEWTIME_MAX, Defaults.VIEWTIME_MAX)),
            headless=settings.get(SettingsKeys.HEADLESS, Defaults.HEADLESS),
            verify_ssl=settings.get(SettingsKeys.VERIFY_SSL, Defaults.VERIFY_SSL),
            engine_mode=engine_mode,
            browser=TrafficConfigBuilder._build_browser_config(settings),
            captcha=TrafficConfigBuilder._build_captcha_config(settings),
            protection=TrafficConfigBuilder._build_protection_config(settings),
            burst_mode=settings.get(SettingsKeys.BURST_MODE, Defaults.BURST_MODE),
            burst_requests=int(settings.get(SettingsKeys.BURST_REQUESTS, Defaults.BURST_REQUESTS)),
            burst_sleep_min=float(settings.get(SettingsKeys.BURST_SLEEP_MIN, Defaults.BURST_SLEEP_MIN)),
            burst_sleep_max=float(settings.get(SettingsKeys.BURST_SLEEP_MAX, Defaults.BURST_SLEEP_MAX)),
        )

    @staticmethod
    def _build_browser_config(settings: dict[str, Any]) -> BrowserConfig:
        """Helper to build BrowserConfig from settings."""
        selected_str = settings.get(
            SettingsKeys.BROWSER_SELECTED, Defaults.BROWSER_SELECTED
        )
        selected_enum = TrafficConfigBuilder.BROWSER_SELECTION_MAP.get(
            selected_str, BrowserSelection.AUTO
        )

        return BrowserConfig(
            selected_browser=selected_enum,
            chrome_path=settings.get(
                SettingsKeys.BROWSER_CHROME_PATH, Defaults.BROWSER_CHROME_PATH
            ),
            chromium_path=settings.get(
                SettingsKeys.BROWSER_CHROMIUM_PATH, Defaults.BROWSER_CHROMIUM_PATH
            ),
            edge_path=settings.get(
                SettingsKeys.BROWSER_EDGE_PATH, Defaults.BROWSER_EDGE_PATH
            ),
            brave_path=settings.get(
                SettingsKeys.BROWSER_BRAVE_PATH, Defaults.BROWSER_BRAVE_PATH
            ),
            firefox_path=settings.get(
                SettingsKeys.BROWSER_FIREFOX_PATH, Defaults.BROWSER_FIREFOX_PATH
            ),
            other_path=settings.get(
                SettingsKeys.BROWSER_OTHER_PATH, Defaults.BROWSER_OTHER_PATH
            ),
            headless=settings.get(SettingsKeys.HEADLESS, Defaults.HEADLESS),
            max_contexts=int(settings.get(
                SettingsKeys.BROWSER_CONTEXTS, Defaults.BROWSER_CONTEXTS
            )),
            locale=settings.get(SettingsKeys.BROWSER_LOCALE, Defaults.BROWSER_LOCALE),
            timezone=settings.get(
                SettingsKeys.BROWSER_TIMEZONE, Defaults.BROWSER_TIMEZONE
            ),
            stealth_enabled=settings.get(
                SettingsKeys.BROWSER_STEALTH, Defaults.BROWSER_STEALTH
            ),
        )

    @staticmethod
    def _build_captcha_config(settings: dict[str, Any]) -> CaptchaConfig:
        """Helper to build CaptchaConfig from settings."""
        provider_str = settings.get(
            SettingsKeys.CAPTCHA_PRIMARY, Defaults.CAPTCHA_PRIMARY
        )
        provider_enum = TrafficConfigBuilder.CAPTCHA_PROVIDER_MAP.get(
            provider_str, CaptchaProvider.AUTO
        )

        return CaptchaConfig(
            twocaptcha_key=settings.get(
                SettingsKeys.CAPTCHA_2CAPTCHA_KEY, Defaults.CAPTCHA_2CAPTCHA_KEY
            ),
            anticaptcha_key=settings.get(
                SettingsKeys.CAPTCHA_ANTICAPTCHA_KEY, Defaults.CAPTCHA_ANTICAPTCHA_KEY
            ),
            primary_provider=provider_enum,
            fallback_enabled=settings.get(
                SettingsKeys.CAPTCHA_FALLBACK_ENABLED, Defaults.CAPTCHA_FALLBACK_ENABLED
            ),
            timeout_seconds=int(settings.get(
                SettingsKeys.CAPTCHA_TIMEOUT, Defaults.CAPTCHA_TIMEOUT
            )),
        )

    @staticmethod
    def _build_protection_config(settings: dict[str, Any]) -> ProtectionBypassConfig:
        """Helper to build ProtectionBypassConfig from settings."""
        return ProtectionBypassConfig(
            cloudflare_enabled=settings.get(
                SettingsKeys.CLOUDFLARE_BYPASS, Defaults.CLOUDFLARE_BYPASS
            ),
            cloudflare_wait_seconds=int(settings.get(
                SettingsKeys.CLOUDFLARE_WAIT, Defaults.CLOUDFLARE_WAIT
            )),
            akamai_enabled=settings.get(
                SettingsKeys.AKAMAI_BYPASS, Defaults.AKAMAI_BYPASS
            ),
            auto_solve_captcha=settings.get(
                SettingsKeys.AUTO_SOLVE_CAPTCHA, Defaults.AUTO_SOLVE_CAPTCHA
            ),
        )
