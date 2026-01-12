"""
Captcha solving integration for 2captcha and AntiCaptcha services.
Supports Cloudflare Turnstile, reCAPTCHA v2/v3, and hCaptcha.
"""
import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

# aiohttp is optional - check availability
aiohttp_available = False
try:
    import aiohttp
    aiohttp_available = True
except ImportError:
    pass


@dataclass
class CaptchaSolution:
    """Result of a captcha solve attempt."""
    success: bool
    token: str | None = None
    error: str | None = None
    solve_time_ms: int = 0


class CaptchaSolverBase(ABC):
    """Abstract base class for captcha solving providers."""

    def __init__(self, api_key: str, timeout: int = 120):
        """
        Initialize solver.

        Args:
            api_key: API key for the captcha service
            timeout: Max seconds to wait for solution
        """
        if not aiohttp_available:
            raise ImportError("aiohttp is required for captcha solving. Run: pip install aiohttp")

        self.api_key = api_key
        self.timeout = timeout

    @abstractmethod
    async def solve_turnstile(self, site_key: str, page_url: str) -> CaptchaSolution:
        """Solve Cloudflare Turnstile challenge."""
        pass

    @abstractmethod
    async def solve_recaptcha_v2(self, site_key: str, page_url: str) -> CaptchaSolution:
        """Solve Google reCAPTCHA v2 challenge."""
        pass

    @abstractmethod
    async def solve_recaptcha_v3(self, site_key: str, page_url: str, action: str = "verify") -> CaptchaSolution:
        """Solve Google reCAPTCHA v3 challenge."""
        pass

    @abstractmethod
    async def solve_hcaptcha(self, site_key: str, page_url: str) -> CaptchaSolution:
        """Solve hCaptcha challenge."""
        pass

    @abstractmethod
    async def get_balance(self) -> float:
        """Get account balance."""
        pass


class TwoCaptchaSolver(CaptchaSolverBase):
    """2captcha.com API implementation."""

    BASE_URL = "https://2captcha.com"

    async def _submit_task(self, session: aiohttp.ClientSession, params: dict) -> str | None:
        """Submit a captcha task and return task ID."""
        params["key"] = self.api_key
        params["json"] = 1

        async with session.get(f"{self.BASE_URL}/in.php", params=params) as resp:
            data = await resp.json()
            if data.get("status") == 1:
                return data.get("request")
            else:
                logging.warning(f"2captcha submit error: {data.get('request')}")
                return None

    async def _poll_result(self, session: aiohttp.ClientSession, task_id: str) -> CaptchaSolution:
        """Poll for task result."""
        start = time.time()
        params = {"key": self.api_key, "action": "get", "id": task_id, "json": 1}

        for _ in range(self.timeout // 5):
            await asyncio.sleep(5)

            async with session.get(f"{self.BASE_URL}/res.php", params=params) as resp:
                data = await resp.json()

                if data.get("status") == 1:
                    solve_time = int((time.time() - start) * 1000)
                    return CaptchaSolution(
                        success=True,
                        token=data["request"],
                        solve_time_ms=solve_time
                    )
                elif data.get("request") != "CAPCHA_NOT_READY":
                    return CaptchaSolution(success=False, error=data.get("request"))

        return CaptchaSolution(success=False, error="Timeout waiting for solution")

    async def solve_turnstile(self, site_key: str, page_url: str) -> CaptchaSolution:
        """Solve Cloudflare Turnstile."""
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "method": "turnstile",
                    "sitekey": site_key,
                    "pageurl": page_url,
                }
                task_id = await self._submit_task(session, params)
                if not task_id:
                    return CaptchaSolution(success=False, error="Failed to submit task")

                return await self._poll_result(session, task_id)

        except Exception as e:
            return CaptchaSolution(success=False, error=str(e))

    async def solve_recaptcha_v2(self, site_key: str, page_url: str) -> CaptchaSolution:
        """Solve reCAPTCHA v2."""
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "method": "userrecaptcha",
                    "googlekey": site_key,
                    "pageurl": page_url,
                }
                task_id = await self._submit_task(session, params)
                if not task_id:
                    return CaptchaSolution(success=False, error="Failed to submit task")

                return await self._poll_result(session, task_id)

        except Exception as e:
            return CaptchaSolution(success=False, error=str(e))

    async def solve_recaptcha_v3(self, site_key: str, page_url: str, action: str = "verify") -> CaptchaSolution:
        """Solve reCAPTCHA v3."""
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "method": "userrecaptcha",
                    "googlekey": site_key,
                    "pageurl": page_url,
                    "version": "v3",
                    "action": action,
                    "min_score": 0.3,
                }
                task_id = await self._submit_task(session, params)
                if not task_id:
                    return CaptchaSolution(success=False, error="Failed to submit task")

                return await self._poll_result(session, task_id)

        except Exception as e:
            return CaptchaSolution(success=False, error=str(e))

    async def solve_hcaptcha(self, site_key: str, page_url: str) -> CaptchaSolution:
        """Solve hCaptcha."""
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "method": "hcaptcha",
                    "sitekey": site_key,
                    "pageurl": page_url,
                }
                task_id = await self._submit_task(session, params)
                if not task_id:
                    return CaptchaSolution(success=False, error="Failed to submit task")

                return await self._poll_result(session, task_id)

        except Exception as e:
            return CaptchaSolution(success=False, error=str(e))

    async def get_balance(self) -> float:
        """Get account balance."""
        try:
            async with aiohttp.ClientSession() as session:
                params = {"key": self.api_key, "action": "getbalance", "json": 1}
                async with session.get(f"{self.BASE_URL}/res.php", params=params) as resp:
                    data = await resp.json()
                    if data.get("status") == 1:
                        return float(data.get("request", 0))
                    return 0.0
        except Exception as e:
            logging.warning(f"Failed to get 2captcha balance: {e}")
            return 0.0


class AntiCaptchaSolver(CaptchaSolverBase):
    """anti-captcha.com API implementation."""

    BASE_URL = "https://api.anti-captcha.com"

    async def _create_task(self, session: aiohttp.ClientSession, task: dict) -> int | None:
        """Create a task and return task ID."""
        payload = {
            "clientKey": self.api_key,
            "task": task,
        }

        async with session.post(f"{self.BASE_URL}/createTask", json=payload) as resp:
            data = await resp.json()
            if data.get("errorId") == 0:
                return data.get("taskId")
            else:
                logging.warning(f"AntiCaptcha create error: {data.get('errorDescription')}")
                return None

    async def _get_result(self, session: aiohttp.ClientSession, task_id: int) -> CaptchaSolution:
        """Poll for task result."""
        start = time.time()
        payload = {"clientKey": self.api_key, "taskId": task_id}

        for _ in range(self.timeout // 5):
            await asyncio.sleep(5)

            async with session.post(f"{self.BASE_URL}/getTaskResult", json=payload) as resp:
                data = await resp.json()

                if data.get("status") == "ready":
                    solution = data.get("solution", {})
                    token = solution.get("gRecaptchaResponse") or solution.get("token")
                    solve_time = int((time.time() - start) * 1000)
                    return CaptchaSolution(
                        success=True,
                        token=token,
                        solve_time_ms=solve_time
                    )
                elif data.get("errorId") != 0:
                    return CaptchaSolution(success=False, error=data.get("errorDescription"))

        return CaptchaSolution(success=False, error="Timeout waiting for solution")

    async def solve_turnstile(self, site_key: str, page_url: str) -> CaptchaSolution:
        """Solve Cloudflare Turnstile."""
        try:
            async with aiohttp.ClientSession() as session:
                task = {
                    "type": "TurnstileTaskProxyless",
                    "websiteURL": page_url,
                    "websiteKey": site_key,
                }
                task_id = await self._create_task(session, task)
                if not task_id:
                    return CaptchaSolution(success=False, error="Failed to create task")

                return await self._get_result(session, task_id)

        except Exception as e:
            return CaptchaSolution(success=False, error=str(e))

    async def solve_recaptcha_v2(self, site_key: str, page_url: str) -> CaptchaSolution:
        """Solve reCAPTCHA v2."""
        try:
            async with aiohttp.ClientSession() as session:
                task = {
                    "type": "RecaptchaV2TaskProxyless",
                    "websiteURL": page_url,
                    "websiteKey": site_key,
                }
                task_id = await self._create_task(session, task)
                if not task_id:
                    return CaptchaSolution(success=False, error="Failed to create task")

                return await self._get_result(session, task_id)

        except Exception as e:
            return CaptchaSolution(success=False, error=str(e))

    async def solve_recaptcha_v3(self, site_key: str, page_url: str, action: str = "verify") -> CaptchaSolution:
        """Solve reCAPTCHA v3."""
        try:
            async with aiohttp.ClientSession() as session:
                task = {
                    "type": "RecaptchaV3TaskProxyless",
                    "websiteURL": page_url,
                    "websiteKey": site_key,
                    "pageAction": action,
                    "minScore": 0.3,
                }
                task_id = await self._create_task(session, task)
                if not task_id:
                    return CaptchaSolution(success=False, error="Failed to create task")

                return await self._get_result(session, task_id)

        except Exception as e:
            return CaptchaSolution(success=False, error=str(e))

    async def solve_hcaptcha(self, site_key: str, page_url: str) -> CaptchaSolution:
        """Solve hCaptcha."""
        try:
            async with aiohttp.ClientSession() as session:
                task = {
                    "type": "HCaptchaTaskProxyless",
                    "websiteURL": page_url,
                    "websiteKey": site_key,
                }
                task_id = await self._create_task(session, task)
                if not task_id:
                    return CaptchaSolution(success=False, error="Failed to create task")

                return await self._get_result(session, task_id)

        except Exception as e:
            return CaptchaSolution(success=False, error=str(e))

    async def get_balance(self) -> float:
        """Get account balance."""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"clientKey": self.api_key}
                async with session.post(f"{self.BASE_URL}/getBalance", json=payload) as resp:
                    data = await resp.json()
                    if data.get("errorId") == 0:
                        return float(data.get("balance", 0))
                    return 0.0
        except Exception as e:
            logging.warning(f"Failed to get AntiCaptcha balance: {e}")
            return 0.0


def create_solver(provider: str, api_key: str, timeout: int = 120) -> CaptchaSolverBase | None:
    """
    Factory function to create appropriate captcha solver.

    Args:
        provider: Provider name ("2captcha" or "anticaptcha")
        api_key: API key for the service
        timeout: Max seconds to wait for solution

    Returns:
        CaptchaSolverBase instance or None if provider not recognized
    """
    if provider == "2captcha":
        return TwoCaptchaSolver(api_key, timeout)
    elif provider == "anticaptcha":
        return AntiCaptchaSolver(api_key, timeout)
    else:
        logging.warning(f"Unknown captcha provider: {provider}")
        return None
