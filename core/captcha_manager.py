"""
Intelligent captcha solving manager with multi-provider support and fallback.
Handles provider selection based on captcha type and automatic fallback on failure.
"""
import logging
from typing import Optional, Dict
from .models import CaptchaConfig, CaptchaProvider, CaptchaType
from .captcha_solver import (
    CaptchaSolution,
    CaptchaSolverBase,
    TwoCaptchaSolver,
    AntiCaptchaSolver,
    aiohttp_available
)


# Provider strengths/preferences by captcha type
# Based on general reliability and speed for each captcha type
PROVIDER_PREFERENCES: Dict[CaptchaType, list] = {
    CaptchaType.TURNSTILE: [CaptchaProvider.TWOCAPTCHA, CaptchaProvider.ANTICAPTCHA],
    CaptchaType.RECAPTCHA_V2: [CaptchaProvider.ANTICAPTCHA, CaptchaProvider.TWOCAPTCHA],
    CaptchaType.RECAPTCHA_V3: [CaptchaProvider.TWOCAPTCHA, CaptchaProvider.ANTICAPTCHA],
    CaptchaType.HCAPTCHA: [CaptchaProvider.ANTICAPTCHA, CaptchaProvider.TWOCAPTCHA],
}


class CaptchaManager:
    """
    Manages multiple captcha solving providers with intelligent selection and fallback.

    Features:
    - Dual provider support (2captcha + AntiCaptcha)
    - Intelligent provider selection based on captcha type
    - Automatic fallback on failure
    - Balance checking for both providers
    """

    def __init__(self, config: CaptchaConfig):
        """
        Initialize captcha manager with configuration.

        Args:
            config: CaptchaConfig with API keys and preferences
        """
        if not aiohttp_available:
            raise ImportError("aiohttp is required for captcha solving. Run: pip install aiohttp")

        self.config = config
        self._solvers: Dict[CaptchaProvider, CaptchaSolverBase] = {}

        # Initialize available solvers
        if config.twocaptcha_key:
            self._solvers[CaptchaProvider.TWOCAPTCHA] = TwoCaptchaSolver(
                config.twocaptcha_key,
                config.timeout_seconds
            )
            logging.info("2captcha solver initialized")

        if config.anticaptcha_key:
            self._solvers[CaptchaProvider.ANTICAPTCHA] = AntiCaptchaSolver(
                config.anticaptcha_key,
                config.timeout_seconds
            )
            logging.info("AntiCaptcha solver initialized")

    def has_solver(self) -> bool:
        """Check if any solver is available."""
        return len(self._solvers) > 0

    def get_available_providers(self) -> list:
        """Get list of available provider names."""
        return list(self._solvers.keys())

    def _get_solver_order(self, captcha_type: CaptchaType) -> list:
        """
        Get ordered list of solvers to try based on captcha type and config.

        Args:
            captcha_type: Type of captcha being solved

        Returns:
            List of CaptchaSolverBase instances in priority order
        """
        solvers = []

        # If specific primary provider is set (not AUTO)
        if self.config.primary_provider not in (CaptchaProvider.AUTO, CaptchaProvider.NONE):
            if self.config.primary_provider in self._solvers:
                solvers.append(self._solvers[self.config.primary_provider])

            # Add fallback if enabled
            if self.config.fallback_enabled:
                for provider, solver in self._solvers.items():
                    if provider != self.config.primary_provider:
                        solvers.append(solver)
        else:
            # AUTO mode - use type-based preferences
            preferred_order = PROVIDER_PREFERENCES.get(
                captcha_type,
                [CaptchaProvider.TWOCAPTCHA, CaptchaProvider.ANTICAPTCHA]
            )

            for provider in preferred_order:
                if provider in self._solvers:
                    solvers.append(self._solvers[provider])

        return solvers

    async def solve_turnstile(self, site_key: str, page_url: str) -> CaptchaSolution:
        """
        Solve Cloudflare Turnstile with automatic provider selection and fallback.

        Args:
            site_key: Turnstile site key
            page_url: URL where captcha appears

        Returns:
            CaptchaSolution with result
        """
        solvers = self._get_solver_order(CaptchaType.TURNSTILE)

        if not solvers:
            return CaptchaSolution(success=False, error="No captcha solver configured")

        last_error = None
        for solver in solvers:
            try:
                provider_name = type(solver).__name__
                logging.info(f"Attempting Turnstile solve with {provider_name}")

                result = await solver.solve_turnstile(site_key, page_url)

                if result.success:
                    logging.info(f"Turnstile solved successfully by {provider_name}")
                    return result
                else:
                    last_error = result.error
                    logging.warning(f"{provider_name} failed: {result.error}")

                    if not self.config.fallback_enabled:
                        break

            except Exception as e:
                last_error = str(e)
                logging.warning(f"Solver exception: {e}")

                if not self.config.fallback_enabled:
                    break

        return CaptchaSolution(success=False, error=f"All solvers failed: {last_error}")

    async def solve_recaptcha_v2(self, site_key: str, page_url: str) -> CaptchaSolution:
        """
        Solve reCAPTCHA v2 with automatic provider selection and fallback.

        Args:
            site_key: reCAPTCHA site key
            page_url: URL where captcha appears

        Returns:
            CaptchaSolution with result
        """
        solvers = self._get_solver_order(CaptchaType.RECAPTCHA_V2)

        if not solvers:
            return CaptchaSolution(success=False, error="No captcha solver configured")

        last_error = None
        for solver in solvers:
            try:
                provider_name = type(solver).__name__
                logging.info(f"Attempting reCAPTCHA v2 solve with {provider_name}")

                result = await solver.solve_recaptcha_v2(site_key, page_url)

                if result.success:
                    logging.info(f"reCAPTCHA v2 solved successfully by {provider_name}")
                    return result
                else:
                    last_error = result.error
                    logging.warning(f"{provider_name} failed: {result.error}")

                    if not self.config.fallback_enabled:
                        break

            except Exception as e:
                last_error = str(e)
                logging.warning(f"Solver exception: {e}")

                if not self.config.fallback_enabled:
                    break

        return CaptchaSolution(success=False, error=f"All solvers failed: {last_error}")

    async def solve_recaptcha_v3(
        self, site_key: str, page_url: str, action: str = "verify"
    ) -> CaptchaSolution:
        """
        Solve reCAPTCHA v3 with automatic provider selection and fallback.

        Args:
            site_key: reCAPTCHA site key
            page_url: URL where captcha appears
            action: reCAPTCHA action parameter

        Returns:
            CaptchaSolution with result
        """
        solvers = self._get_solver_order(CaptchaType.RECAPTCHA_V3)

        if not solvers:
            return CaptchaSolution(success=False, error="No captcha solver configured")

        last_error = None
        for solver in solvers:
            try:
                provider_name = type(solver).__name__
                logging.info(f"Attempting reCAPTCHA v3 solve with {provider_name}")

                result = await solver.solve_recaptcha_v3(site_key, page_url, action)

                if result.success:
                    logging.info(f"reCAPTCHA v3 solved successfully by {provider_name}")
                    return result
                else:
                    last_error = result.error
                    logging.warning(f"{provider_name} failed: {result.error}")

                    if not self.config.fallback_enabled:
                        break

            except Exception as e:
                last_error = str(e)
                logging.warning(f"Solver exception: {e}")

                if not self.config.fallback_enabled:
                    break

        return CaptchaSolution(success=False, error=f"All solvers failed: {last_error}")

    async def solve_hcaptcha(self, site_key: str, page_url: str) -> CaptchaSolution:
        """
        Solve hCaptcha with automatic provider selection and fallback.

        Args:
            site_key: hCaptcha site key
            page_url: URL where captcha appears

        Returns:
            CaptchaSolution with result
        """
        solvers = self._get_solver_order(CaptchaType.HCAPTCHA)

        if not solvers:
            return CaptchaSolution(success=False, error="No captcha solver configured")

        last_error = None
        for solver in solvers:
            try:
                provider_name = type(solver).__name__
                logging.info(f"Attempting hCaptcha solve with {provider_name}")

                result = await solver.solve_hcaptcha(site_key, page_url)

                if result.success:
                    logging.info(f"hCaptcha solved successfully by {provider_name}")
                    return result
                else:
                    last_error = result.error
                    logging.warning(f"{provider_name} failed: {result.error}")

                    if not self.config.fallback_enabled:
                        break

            except Exception as e:
                last_error = str(e)
                logging.warning(f"Solver exception: {e}")

                if not self.config.fallback_enabled:
                    break

        return CaptchaSolution(success=False, error=f"All solvers failed: {last_error}")

    async def get_balances(self) -> Dict[str, float]:
        """
        Get balance from all configured providers.

        Returns:
            Dict mapping provider name to balance
        """
        balances = {}

        if CaptchaProvider.TWOCAPTCHA in self._solvers:
            try:
                balance = await self._solvers[CaptchaProvider.TWOCAPTCHA].get_balance()
                balances["2captcha"] = balance
            except Exception as e:
                logging.warning(f"Failed to get 2captcha balance: {e}")
                balances["2captcha"] = -1

        if CaptchaProvider.ANTICAPTCHA in self._solvers:
            try:
                balance = await self._solvers[CaptchaProvider.ANTICAPTCHA].get_balance()
                balances["anticaptcha"] = balance
            except Exception as e:
                logging.warning(f"Failed to get AntiCaptcha balance: {e}")
                balances["anticaptcha"] = -1

        return balances

    async def get_balance(self, provider: Optional[CaptchaProvider] = None) -> float:
        """
        Get balance from a specific provider or primary provider.

        Args:
            provider: Specific provider to check, or None for primary

        Returns:
            Balance amount or 0 on error
        """
        if provider is None:
            # Use primary or first available
            if self.config.primary_provider in self._solvers:
                provider = self.config.primary_provider
            elif self._solvers:
                provider = list(self._solvers.keys())[0]
            else:
                return 0.0

        if provider in self._solvers:
            try:
                return await self._solvers[provider].get_balance()
            except Exception as e:
                logging.warning(f"Failed to get balance: {e}")

        return 0.0


def create_captcha_manager(config: CaptchaConfig) -> Optional[CaptchaManager]:
    """
    Factory function to create CaptchaManager if any provider is configured.

    Args:
        config: CaptchaConfig with API keys

    Returns:
        CaptchaManager instance or None if no providers configured
    """
    if not config.has_any_provider():
        return None

    try:
        return CaptchaManager(config)
    except ImportError as e:
        logging.warning(f"Could not create captcha manager: {e}")
        return None
