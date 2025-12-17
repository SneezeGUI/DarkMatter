import asyncio
import random
import logging
from typing import List, Callable, Optional
from curl_cffi import requests
from .models import TrafficConfig, ProxyConfig, TrafficStats
from .constants import (
    BROWSER_IMPERSONATIONS,
    BROWSER_HEADERS,
    DEFAULT_REFERERS,
    REQUEST_TIMEOUT_SECONDS,
    PROXY_ERROR_CODES,
    SUCCESS_STATUS_CODES,
)


class AsyncTrafficEngine:
    def __init__(self, config: TrafficConfig, proxies: List[ProxyConfig], on_update: Optional[Callable[[TrafficStats], None]] = None):
        self.config = config
        self.proxies = proxies
        self.on_update = on_update
        self.stats = TrafficStats()
        self.running = False
        self._stop_event = asyncio.Event()
        self._initial_proxy_count = len(proxies)

    async def _make_request(self):
        """Performs a single visit using a random proxy and browser impersonation."""
        if not self.running:
            return

        if self._initial_proxy_count > 0 and not self.proxies:
            logging.error("No active proxies remaining. Stopping engine.")
            self.running = False
            return

        proxy = None
        proxy_config = None
        if self.proxies:
            # Weighted random selection based on proxy score
            try:
                # Use score as weight, minimum 0.1 to give even bad proxies a small chance
                weights = [max(p.score, 0.1) for p in self.proxies]
                proxy_config = random.choices(self.proxies, weights=weights, k=1)[0]
            except (ValueError, IndexError):
                # Fallback if calculation fails
                proxy_config = random.choice(self.proxies)

            proxy = proxy_config.to_curl_cffi_format()

        # Randomize impersonation
        impersonate = random.choice(BROWSER_IMPERSONATIONS)

        session = None
        try:
            self.stats.active_threads += 1
            if self.on_update:
                self.stats.active_proxies = len(self.proxies)
                self.on_update(self.stats)

            # Create fresh session for each request (clean cookies/TLS state per "user")
            session = requests.AsyncSession(impersonate=impersonate)

            # Set proxy for this request
            proxies_dict = {"http": proxy, "https": proxy} if proxy else None

            # Use browser-consistent headers (User-Agent is set by curl_cffi impersonate)
            headers = BROWSER_HEADERS.copy()
            headers["Referer"] = random.choice(DEFAULT_REFERERS)

            logging.debug(f"Request to {self.config.target_url} via {impersonate}")

            response = await session.get(
                self.config.target_url,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
                verify=self.config.verify_ssl,
                proxies=proxies_dict
            )

            if response.status_code in SUCCESS_STATUS_CODES:
                self.stats.success += 1
                logging.debug(f"Success: {response.status_code}")
            else:
                self.stats.failed += 1
                logging.warning(f"Failed with status: {response.status_code}")

            # Simulate reading/view time
            if self.running:
                view_time = random.uniform(self.config.min_duration, self.config.max_duration)
                await asyncio.sleep(view_time)

        except Exception as e:
            self.stats.failed += 1
            err_msg = str(e)

            # Identify fatal proxy errors
            is_proxy_error = any(code in err_msg for code in PROXY_ERROR_CODES)

            if is_proxy_error and proxy_config:
                logging.warning(f"Proxy Failure: {err_msg}")
                if self.proxies and proxy_config in self.proxies:
                    try:
                        self.proxies.remove(proxy_config)
                        remaining = len(self.proxies)
                        logging.warning(f"Removed dead proxy {proxy_config.host}. Remaining: {remaining}")
                        if remaining == 0:
                            logging.error("CRITICAL: All proxies removed! Stopping.")
                            self.running = False
                    except ValueError:
                        pass  # Already removed
            elif "curl: (60)" in err_msg:
                logging.warning(f"SSL/TLS Error: {err_msg}")
            else:
                logging.debug(f"Request Error: {err_msg}")
        finally:
            # Clean up session
            if session:
                try:
                    await session.close()
                except Exception:
                    pass
            self.stats.active_threads -= 1
            self.stats.total_requests += 1
            if self.on_update:
                self.stats.active_proxies = len(self.proxies)
                self.on_update(self.stats)

    async def run(self):
        """Main loop to spawn workers."""
        self.running = True
        self.stats = TrafficStats()  # Reset stats
        logging.info("Engine started.")

        tasks = set()

        try:
            while self.running:
                # Replenish tasks up to max_threads
                while len(tasks) < self.config.max_threads and self.running:
                    if self.config.total_visits > 0 and self.stats.total_requests >= self.config.total_visits:
                        self.running = False
                        break

                    task = asyncio.create_task(self._make_request())
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)

                if not self.running:
                    break

                await asyncio.sleep(0.1)  # Prevent tight loop

            # Wait for pending tasks to finish gracefully
            if tasks:
                await asyncio.wait(tasks, timeout=5)

        finally:
            logging.info("Engine stopped.")

    def stop(self):
        self.running = False
