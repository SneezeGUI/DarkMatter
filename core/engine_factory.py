"""
Engine factory for creating traffic engine instances.

This module provides a factory pattern for instantiating traffic engines
based on the selected engine mode, with graceful fallback handling.
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from core.engine import AsyncTrafficEngine
from core.models import EngineMode, ProxyConfig, TrafficConfig, TrafficStats

if TYPE_CHECKING:
    from core.session_manager import SessionManager


class TrafficEngine(Protocol):
    """Protocol defining the interface for traffic engines."""
    async def run(self) -> None:
        """Start the traffic generation engine."""
        ...

    def stop(self) -> None:
        """Stop the traffic generation engine."""
        ...

class EngineFactory:
    """Factory for creating traffic engine instances based on configuration."""

    @staticmethod
    def create_engine(
        mode: EngineMode,
        config: TrafficConfig,
        proxies: list[ProxyConfig],
        on_update: Callable[[TrafficStats], None] | None = None,
        on_log: Callable[[str], None] | None = None,
        session_manager: "SessionManager | None" = None,
    ) -> TrafficEngine:
        """
        Create and return the appropriate traffic engine based on mode.

        Args:
            mode: EngineMode.CURL for fast requests, EngineMode.BROWSER for browser automation.
            config: TrafficConfig with all campaign settings.
            proxies: List of ProxyConfig objects for the engine to use.
            on_update: Callback function receiving TrafficStats updates.
            on_log: Callback function receiving log messages.
            session_manager: Optional SessionManager for cookie persistence.

        Returns:
            An engine instance (AsyncTrafficEngine or PlaywrightTrafficEngine).

        Note:
            If PlaywrightTrafficEngine fails to import or initialize (e.g. Playwright not installed),
            it gracefully falls back to AsyncTrafficEngine and logs a warning.
        """
        if mode == EngineMode.BROWSER:
            try:
                # Lazy import to avoid hard dependency if not used or available
                from core.browser_engine import PlaywrightTrafficEngine

                # Attempt to instantiate (this may raise ImportError if playwright is missing)
                return PlaywrightTrafficEngine(
                    config=config,
                    proxies=proxies,
                    on_update=on_update,
                    on_log=on_log,
                    session_manager=session_manager,
                )
            except ImportError as e:
                msg = f"Browser engine unavailable ({str(e)}). Falling back to Fast (CURL) engine."
                logging.warning(msg)
                if on_log:
                    on_log(f"WARNING: {msg}")

                # Update config to reflect fallback
                config.engine_mode = EngineMode.CURL
                # Continue to fallback block below

        # Default to AsyncTrafficEngine (CURL mode or fallback)
        return AsyncTrafficEngine(
            config=config,
            proxies=proxies,
            on_update=on_update,
            on_log=on_log,
            session_manager=session_manager,
        )
