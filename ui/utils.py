import json
import logging
import os
from typing import Any
from urllib.parse import urlparse


class Utils:
    @staticmethod
    def validate_url(url: str) -> bool:
        """Validate that a URL has proper scheme and netloc."""
        if not url:
            return False
        try:
            result = urlparse(url)
            return all([result.scheme in ('http', 'https'), result.netloc])
        except (ValueError, AttributeError):
            return False

    @staticmethod
    def safe_int(value: Any, default: int, min_val: int | None = None, max_val: int | None = None) -> int:
        """Safely convert value to int with optional bounds clamping."""
        try:
            v = int(value)
            if min_val is not None:
                v = max(v, min_val)
            if max_val is not None:
                v = min(v, max_val)
            return v
        except (ValueError, TypeError):
            return default

    @staticmethod
    def get_flag(code: str | None) -> str:
        """Convert a 2-letter country code to a flag emoji."""
        if not code or len(code) != 2:
            return "🏳️"
        try:
            return chr(ord(code[0].upper()) + 127397) + chr(ord(code[1].upper()) + 127397)
        except (ValueError, TypeError):
            return "🏳️"

    @staticmethod
    def load_settings(filename: str = "resources/settings.json") -> dict[str, Any]:
        """Load settings from JSON file, returning defaults if file doesn't exist."""
        defaults: dict[str, Any] = {
            "target_url": "https://example.com",
            "threads": 5,
            "viewtime_min": 5,
            "viewtime_max": 10,
            "proxy_test_url": "https://httpbin.org/get",
            "proxy_timeout": 3000,
            "proxy_check_threads": 50,
            "proxy_scrape_threads": 20,
            "system_proxy": "",
            "system_proxy_protocol": "http",
            "use_proxy_for_scrape": False,
            "use_proxy_for_check": False,
            "use_manual_target": True,  # When False, use validators from settings instead
            "use_http": True,
            "use_socks4": True,
            "use_socks5": True,
            "hide_dead": True,
            "headless": True,
            "verify_ssl": True,
            "sources": "resources/sources.txt",
            # Engine mode settings
            "engine_mode": "curl",  # "curl" or "browser"
            # Browser settings - individual paths for each browser
            "browser_selected": "auto",  # "auto", "chrome", "chromium", "edge", "brave", "firefox", "other"
            "browser_chrome_path": "",
            "browser_chromium_path": "",  # Open-source Chromium / Playwright bundled
            "browser_edge_path": "",
            "browser_brave_path": "",
            "browser_firefox_path": "",
            "browser_other_path": "",
            "browser_headless": True,
            "browser_contexts": 5,
            "browser_stealth": True,
            "browser_locale": "en-US",
            "browser_timezone": "America/New_York",
            # Captcha settings - dual provider support with fallback
            "captcha_2captcha_key": "",
            "captcha_anticaptcha_key": "",
            "captcha_primary": "auto",  # "auto", "2captcha", "anticaptcha", "none"
            "captcha_fallback_enabled": True,
            "captcha_timeout": 120,
            # Protection bypass settings
            "cloudflare_bypass": True,
            "cloudflare_wait": 10,
            "akamai_bypass": True,
            "auto_solve_captcha": True,
            # Validator settings for anonymity testing
            "validators_enabled": {
                "httpbin.org": True,
                "ip-api.com": True,
                "ipify.org": True,
                "ipinfo.io": False,
                "azenv.net": False,
                "wtfismyip.com": False,
            },
            "validator_test_depth": "quick",  # "quick", "normal", "thorough"
            # Distributed Mode Settings (v3.7.0)
            "mode": "standalone",  # "standalone", "master", "slave"
            "master_host": "127.0.0.1",
            "master_port": 8765,
            "master_secret_key": "",
            "slave_secret_key": "",
            "slave_name": "slave-01",
        }

        # 1. Load from file (overrides defaults)
        settings = defaults.copy()
        if os.path.exists(filename):
            try:
                with open(filename) as f:
                    settings.update(json.load(f))
            except (json.JSONDecodeError, OSError):
                pass

        # 2. Environment variable overrides (highest priority)
        # Mapping: ENV_VAR_NAME -> settings_key
        env_map = {
            "DM_MODE": "mode",
            "DM_MASTER_HOST": "master_host",
            "DM_MASTER_PORT": "master_port",
            "DM_SLAVE_SECRET": "slave_secret_key",
            "DM_SLAVE_NAME": "slave_name",
            "DM_CAPTCHA_2CAPTCHA_KEY": "captcha_2captcha_key",
            "DM_CAPTCHA_ANTICAPTCHA_KEY": "captcha_anticaptcha_key",
            "DM_HEADLESS": "headless",
        }

        for env_key, setting_key in env_map.items():
            if val := os.environ.get(env_key):
                # Type conversion for int/bool
                current_val = defaults.get(setting_key)

                if isinstance(current_val, bool):
                     settings[setting_key] = val.lower() in ('true', '1', 'yes')
                elif isinstance(current_val, int):
                    settings[setting_key] = Utils.safe_int(val, current_val)
                else:
                    settings[setting_key] = val

        return settings

    @staticmethod
    def save_settings(data: dict[str, Any], filename: str = "resources/settings.json") -> None:
        """Save settings dictionary to JSON file."""
        try:
            with open(filename, 'w') as f:
                json.dump(data, f, indent=4)
        except (OSError, TypeError) as e:
            logging.error(f"Failed to save settings: {e}")

    @staticmethod
    def deduplicate_proxies(proxy_strings: list) -> list:
        """
        Deduplicate proxy strings based on (host, port, protocol) tuple.
        Handles formats like 'http://1.2.3.4:80' and '1.2.3.4:80'.
        """
        seen: set = set()
        unique: list = []

        for p_str in proxy_strings:
            if not p_str:
                continue

            p_str = p_str.strip()
            if not p_str:
                continue

            # Parse proxy string
            try:
                if "://" in p_str:
                    parts = p_str.split("://", 1)
                    protocol = parts[0].lower()
                    addr = parts[1]
                else:
                    protocol = "http"
                    addr = p_str

                # Handle auth in proxy (user:pass@host:port)
                if "@" in addr:
                    addr = addr.split("@", 1)[1]

                if ":" in addr:
                    host, port = addr.rsplit(":", 1)
                    key = (host.lower(), port, protocol)

                    if key not in seen:
                        seen.add(key)
                        unique.append(p_str)
            except (ValueError, IndexError):
                continue

        return unique

    @staticmethod
    def save_proxies(proxy_results: list, filename: str = "resources/proxies.json", max_retries: int = 3) -> bool:
        """
        Save checked proxy results to JSON file for persistence.
        Uses atomic write (temp file + rename) to prevent corruption.
        Includes retry logic for Windows file locking issues.

        Args:
            proxy_results: List of ProxyCheckResult-like dicts or objects
            filename: Path to save file
            max_retries: Number of retry attempts on file lock errors

        Returns:
            True if save succeeded, False otherwise
        """
        import time as _time

        # Convert to serializable format first (outside retry loop)
        data = []
        for p in proxy_results:
            if hasattr(p, '__dict__'):
                # It's an object, extract relevant fields
                entry = {
                    "host": p.proxy.host if hasattr(p, 'proxy') else "",
                    "port": p.proxy.port if hasattr(p, 'proxy') else 0,
                    "protocol": p.proxy.protocol if hasattr(p, 'proxy') else "http",
                    "status": p.status if hasattr(p, 'status') else "Unknown",
                    "speed": p.speed if hasattr(p, 'speed') else 0,
                    "type": p.type if hasattr(p, 'type') else "",
                    "country": p.country if hasattr(p, 'country') else "",
                    "country_code": p.country_code if hasattr(p, 'country_code') else "",
                    "city": p.city if hasattr(p, 'city') else "",
                    "anonymity": p.anonymity if hasattr(p, 'anonymity') else "Unknown",
                }
                data.append(entry)
            elif isinstance(p, dict):
                data.append(p)

        # Ensure directory exists
        dir_path = os.path.dirname(filename)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        temp_filename = filename + ".tmp"

        # Retry loop for file operations
        for attempt in range(max_retries):
            try:
                # Atomic write: write to temp file first, then rename
                with open(temp_filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())  # Force write to disk

                # Atomic rename (overwrites existing file)
                if os.path.exists(filename):
                    os.replace(temp_filename, filename)
                else:
                    os.rename(temp_filename, filename)

                logging.info(f"Saved {len(data)} proxies to {filename}")
                return True

            except PermissionError as e:
                # Windows file locking - retry with backoff
                if attempt < max_retries - 1:
                    wait_time = 0.5 * (attempt + 1)  # 0.5s, 1.0s, 1.5s
                    logging.warning(f"File locked, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    _time.sleep(wait_time)
                else:
                    logging.error(f"Failed to save proxies after {max_retries} attempts: {e}")
                    return False

            except (OSError, TypeError) as e:
                logging.error(f"Failed to save proxies: {e}")
                break

        # Clean up temp file if it exists
        try:
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
        except:
            pass

        return False

    @staticmethod
    def load_proxies(filename: str = "resources/proxies.json") -> list:
        """
        Load saved proxy results from JSON file with automatic corruption recovery.

        Args:
            filename: Path to save file

        Returns:
            List of proxy dicts, or empty list if file doesn't exist
        """
        if not os.path.exists(filename):
            return []

        try:
            with open(filename) as f:
                data = json.load(f)
            logging.info(f"Loaded {len(data)} proxies from {filename}")
            return data
        except json.JSONDecodeError as e:
            logging.warning(f"Corrupted proxies file detected: {e}")
            # Attempt automatic recovery
            recovered = Utils._recover_corrupted_json(filename)
            if recovered:
                logging.info(f"Recovered {len(recovered)} proxies from corrupted file")
                # Save recovered data back
                Utils.save_proxies(recovered, filename)
                return recovered
            else:
                logging.error("Could not recover proxies - file will be reset")
                # Backup corrupted file before clearing
                backup_name = filename + ".corrupted"
                try:
                    import shutil
                    shutil.copy(filename, backup_name)
                    logging.info(f"Corrupted file backed up to {backup_name}")
                except:
                    pass
                return []
        except OSError as e:
            logging.error(f"Failed to load proxies: {e}")
            return []

    @staticmethod
    def _recover_corrupted_json(filename: str) -> list:
        """
        Attempt to recover valid proxy entries from a corrupted JSON file.

        Handles common corruption scenarios:
        - Truncated file (write interrupted)
        - Missing closing brackets
        - Incomplete last entry
        """
        try:
            with open(filename, encoding='utf-8') as f:
                content = f.read()
        except:
            return []

        if not content.strip():
            return []

        recovered = []

        # Strategy 1: Try truncating from the end to find valid JSON
        # Look for the last complete object (ends with })
        for i in range(len(content) - 1, 0, -1):
            if content[i] == '}':
                # Try to parse up to this point + closing bracket
                attempt = content[:i+1].rstrip().rstrip(',') + '\n]'
                # Ensure it starts with [
                if not attempt.strip().startswith('['):
                    attempt = '[\n' + attempt
                try:
                    recovered = json.loads(attempt)
                    if isinstance(recovered, list) and len(recovered) > 0:
                        logging.info(f"Recovery Strategy 1: Found {len(recovered)} valid entries")
                        return recovered
                except:
                    continue

        # Strategy 2: Extract individual JSON objects using regex
        import re
        # Match complete proxy objects
        pattern = r'\{\s*"host"\s*:\s*"[^"]+"\s*,\s*"port"\s*:\s*\d+[^}]*\}'
        matches = re.findall(pattern, content, re.DOTALL)

        if matches:
            for match in matches:
                try:
                    obj = json.loads(match)
                    if 'host' in obj and 'port' in obj:
                        recovered.append(obj)
                except:
                    continue

            if recovered:
                logging.info(f"Recovery Strategy 2: Extracted {len(recovered)} valid entries")
                return recovered

        # Strategy 3: Line-by-line recovery (for pretty-printed JSON)
        lines = content.split('\n')
        current_obj = ""
        brace_count = 0

        for line in lines:
            current_obj += line
            brace_count += line.count('{') - line.count('}')

            if brace_count == 0 and '{' in current_obj:
                # We have a complete object
                clean = current_obj.strip().strip(',').strip()
                if clean.startswith('{') and clean.endswith('}'):
                    try:
                        obj = json.loads(clean)
                        if 'host' in obj and 'port' in obj:
                            recovered.append(obj)
                    except:
                        pass
                current_obj = ""

        if recovered:
            logging.info(f"Recovery Strategy 3: Parsed {len(recovered)} valid entries")
            return recovered

        return []

    @staticmethod
    def clear_saved_proxies(filename: str = "resources/proxies.json") -> bool:
        """
        Delete the saved proxies file.

        Args:
            filename: Path to save file

        Returns:
            True if deleted, False otherwise
        """
        try:
            if os.path.exists(filename):
                os.remove(filename)
                logging.info(f"Cleared saved proxies: {filename}")
                return True
        except OSError as e:
            logging.error(f"Failed to clear proxies: {e}")
        return False
