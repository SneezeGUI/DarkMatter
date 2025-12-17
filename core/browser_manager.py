"""
Browser path detection and management for Playwright integration.
Supports auto-detection of system browsers and manual path configuration.
"""
import os
import subprocess
import logging
from typing import Optional, Tuple, List
from dataclasses import dataclass


@dataclass
class BrowserInfo:
    """Information about a detected browser."""
    name: str
    path: str
    browser_type: str = "chromium"  # "chromium" or "firefox" for Playwright
    version: Optional[str] = None
    is_valid: bool = False


class BrowserManager:
    """Manages browser executable detection and validation."""

    # Comprehensive Windows browser paths for all 4 supported browsers
    # Each list covers: Program Files, Program Files (x86), LocalAppData, and user-specific locations

    WINDOWS_CHROME_PATHS = [
        # Standard installations
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
        # User-specific installation
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        # Per-user installation (newer Chrome versions)
        os.path.expandvars(r"%USERPROFILE%\AppData\Local\Google\Chrome\Application\chrome.exe"),
        # Canary/Dev/Beta channels
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome SxS\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome Dev\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome Beta\Application\chrome.exe"),
        # Portable installations (common locations)
        r"C:\Google\Chrome\Application\chrome.exe",
        r"D:\Google\Chrome\Application\chrome.exe",
    ]

    WINDOWS_CHROMIUM_PATHS = [
        # Standard Chromium installations
        os.path.expandvars(r"%LOCALAPPDATA%\Chromium\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Chromium\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Chromium\Application\chrome.exe"),
        # User profile installation
        os.path.expandvars(r"%USERPROFILE%\AppData\Local\Chromium\Application\chrome.exe"),
        # Alternative executable names
        os.path.expandvars(r"%LOCALAPPDATA%\Chromium\Application\chromium.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Chromium\Application\chromium.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Chromium\Application\chromium.exe"),
        # Portable/standalone installations
        r"C:\Chromium\chrome.exe",
        r"D:\Chromium\chrome.exe",
        r"C:\Chromium\chromium.exe",
        r"D:\Chromium\chromium.exe",
        # Playwright bundled Chromium (common location)
        os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright\chromium-*\chrome-win\chrome.exe"),
        # Ungoogled Chromium (popular fork)
        os.path.expandvars(r"%LOCALAPPDATA%\ungoogled-chromium\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\ungoogled-chromium\chrome.exe"),
    ]

    WINDOWS_EDGE_PATHS = [
        # Standard installations
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
        # User-specific installation
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        # Per-user installation
        os.path.expandvars(r"%USERPROFILE%\AppData\Local\Microsoft\Edge\Application\msedge.exe"),
        # Dev/Beta/Canary channels
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge Dev\Application\msedge.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge Beta\Application\msedge.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge SxS\Application\msedge.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge Dev\Application\msedge.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge Beta\Application\msedge.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge SxS\Application\msedge.exe"),
    ]

    WINDOWS_BRAVE_PATHS = [
        # Standard installations
        os.path.expandvars(r"%PROGRAMFILES%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        # User-specific installation (most common for Brave)
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        os.path.expandvars(r"%USERPROFILE%\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe"),
        # Beta/Nightly channels
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser-Beta\Application\brave.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser-Nightly\Application\brave.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\BraveSoftware\Brave-Browser-Beta\Application\brave.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\BraveSoftware\Brave-Browser-Nightly\Application\brave.exe"),
    ]

    WINDOWS_FIREFOX_PATHS = [
        # Standard installations
        os.path.expandvars(r"%PROGRAMFILES%\Mozilla Firefox\firefox.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Mozilla Firefox\firefox.exe"),
        # User-specific installation
        os.path.expandvars(r"%LOCALAPPDATA%\Mozilla Firefox\firefox.exe"),
        os.path.expandvars(r"%USERPROFILE%\AppData\Local\Mozilla Firefox\firefox.exe"),
        # Developer Edition
        os.path.expandvars(r"%PROGRAMFILES%\Firefox Developer Edition\firefox.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Firefox Developer Edition\firefox.exe"),
        # Nightly
        os.path.expandvars(r"%PROGRAMFILES%\Firefox Nightly\firefox.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Firefox Nightly\firefox.exe"),
        # ESR (Extended Support Release)
        os.path.expandvars(r"%PROGRAMFILES%\Mozilla Firefox ESR\firefox.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Mozilla Firefox ESR\firefox.exe"),
        # Portable installations (common locations)
        r"C:\Firefox\firefox.exe",
        r"D:\Firefox\firefox.exe",
        r"C:\Mozilla Firefox\firefox.exe",
        r"D:\Mozilla Firefox\firefox.exe",
    ]

    # Map browser names to Playwright browser types
    BROWSER_TYPES = {
        "Chrome": "chromium",
        "Chromium": "chromium",
        "Edge": "chromium",
        "Brave": "chromium",
        "Firefox": "firefox",
    }

    @classmethod
    def detect_browsers(cls) -> List[BrowserInfo]:
        """
        Detect all installed browsers on Windows (Chrome, Chromium, Edge, Brave, Firefox).
        Returns list of BrowserInfo objects for each found browser.
        """
        found = []

        browser_configs = [
            ("Chrome", cls.WINDOWS_CHROME_PATHS),
            ("Chromium", cls.WINDOWS_CHROMIUM_PATHS),
            ("Edge", cls.WINDOWS_EDGE_PATHS),
            ("Brave", cls.WINDOWS_BRAVE_PATHS),
            ("Firefox", cls.WINDOWS_FIREFOX_PATHS),
        ]

        for name, paths in browser_configs:
            for path in paths:
                if os.path.isfile(path):
                    version = cls._get_browser_version(path)
                    browser_type = cls.BROWSER_TYPES.get(name, "chromium")
                    found.append(BrowserInfo(
                        name=name,
                        path=path,
                        browser_type=browser_type,
                        version=version,
                        is_valid=True
                    ))
                    break  # Found this browser, skip other paths

        return found

    @classmethod
    def _get_browser_version(cls, path: str) -> Optional[str]:
        """
        Attempt to get browser version from executable.
        Returns version string or None if unable to determine.
        """
        try:
            # For Chrome/Edge/Brave, version is often in the path
            # e.g., .../Chrome/Application/120.0.6099.130/...
            parts = path.replace("\\", "/").split("/")
            for part in parts:
                if part and part[0].isdigit() and "." in part:
                    return part

            # Try running with --version flag (works for some browsers)
            result = subprocess.run(
                [path, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.strip().split()[-1]
        except Exception as e:
            logging.debug(f"Could not get version for {path}: {e}")

        return None

    @classmethod
    def validate_browser_path(cls, path: str) -> Tuple[bool, str]:
        """
        Validate a browser executable path.

        Args:
            path: Path to browser executable

        Returns:
            Tuple of (is_valid, message)
        """
        if not path:
            return False, "Path is empty"

        if not os.path.isfile(path):
            return False, f"File not found: {path}"

        # Check file extension
        if not path.lower().endswith('.exe'):
            return False, "Not an executable file (.exe)"

        # Check if it's a known browser executable name
        filename = os.path.basename(path).lower()
        known_browsers = ['chrome.exe', 'msedge.exe', 'brave.exe', 'firefox.exe', 'chromium.exe']

        if filename not in known_browsers:
            # Allow but warn
            logging.warning(f"Unknown browser executable: {filename}")

        return True, "Browser path is valid"

    @classmethod
    def get_default_browser(cls) -> Optional[str]:
        """
        Return path to first detected browser, or None.
        Priority order: Chrome > Edge > Brave > Firefox
        """
        browsers = cls.detect_browsers()
        if browsers:
            return browsers[0].path
        return None

    @classmethod
    def get_browser_type_from_path(cls, path: str) -> str:
        """
        Determine Playwright browser type from executable path.

        Args:
            path: Path to browser executable

        Returns:
            "chromium" or "firefox"
        """
        if not path:
            return "chromium"

        filename = os.path.basename(path).lower()
        if "firefox" in filename:
            return "firefox"
        return "chromium"

    @classmethod
    def get_browser_info_from_path(cls, path: str) -> Optional[BrowserInfo]:
        """
        Get BrowserInfo for a specific path.

        Args:
            path: Path to browser executable

        Returns:
            BrowserInfo object or None if path invalid
        """
        if not path or not os.path.isfile(path):
            return None

        filename = os.path.basename(path).lower()
        # Also check parent directory for context
        parent_dir = os.path.basename(os.path.dirname(path)).lower() if path else ""
        grandparent = os.path.basename(os.path.dirname(os.path.dirname(path))).lower() if path else ""

        # Determine browser name from filename and path context
        # Check for Chromium first (more specific) before Chrome (more general)
        if "chromium" in filename or "chromium" in parent_dir or "chromium" in grandparent:
            name = "Chromium"
        elif "ungoogled" in path.lower():
            name = "Chromium"  # Ungoogled Chromium
        elif "ms-playwright" in path.lower():
            name = "Chromium"  # Playwright bundled Chromium
        elif "chrome" in filename and "google" in path.lower():
            name = "Chrome"  # Google Chrome specifically
        elif "chrome" in filename:
            # Generic chrome.exe - could be Chrome or Chromium, check path
            if "chromium" in path.lower():
                name = "Chromium"
            else:
                name = "Chrome"
        elif "msedge" in filename or "edge" in filename:
            name = "Edge"
        elif "brave" in filename:
            name = "Brave"
        elif "firefox" in filename:
            name = "Firefox"
        else:
            name = "Unknown"

        browser_type = cls.get_browser_type_from_path(path)
        version = cls._get_browser_version(path)

        return BrowserInfo(
            name=name,
            path=path,
            browser_type=browser_type,
            version=version,
            is_valid=True
        )

    @classmethod
    def get_playwright_chromium_path(cls) -> Optional[str]:
        """
        Get path to Playwright's bundled Chromium if installed.
        Returns None if not installed.
        """
        try:
            # Playwright stores browsers in a specific location
            from playwright._impl._driver import compute_driver_executable

            # This is a heuristic - actual path varies by installation
            playwright_cache = os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright")
            if os.path.isdir(playwright_cache):
                # Look for chromium executable
                for root, dirs, files in os.walk(playwright_cache):
                    for f in files:
                        if f == "chrome.exe" or f == "chromium.exe":
                            full_path = os.path.join(root, f)
                            if os.path.isfile(full_path):
                                return full_path
        except Exception as e:
            logging.debug(f"Could not find Playwright Chromium: {e}")

        return None

    @classmethod
    def get_best_browser(cls) -> Tuple[Optional[str], str]:
        """
        Get the best available browser path with source description.

        Returns:
            Tuple of (path, source_description)
            path is None if no browser found
        """
        # Try system browsers first
        default = cls.get_default_browser()
        if default:
            browsers = cls.detect_browsers()
            name = next((b.name for b in browsers if b.path == default), "Browser")
            return default, f"System {name}"

        # Try Playwright bundled browser
        playwright_path = cls.get_playwright_chromium_path()
        if playwright_path:
            return playwright_path, "Playwright Chromium"

        return None, "No browser found"

    @classmethod
    def test_browser_launch(cls, path: str, headless: bool = True) -> Tuple[bool, str]:
        """
        Test if a browser can be launched successfully.

        Args:
            path: Path to browser executable
            headless: Whether to launch in headless mode

        Returns:
            Tuple of (success, message)
        """
        try:
            args = [path]
            if headless:
                args.append("--headless")
            args.extend([
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "about:blank"
            ])

            # Launch and quickly terminate
            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # Wait briefly then terminate
            import time
            time.sleep(1)
            proc.terminate()
            proc.wait(timeout=5)

            return True, "Browser launched successfully"

        except FileNotFoundError:
            return False, f"Browser not found at: {path}"
        except subprocess.TimeoutExpired:
            proc.kill()
            return True, "Browser launched (killed after timeout)"
        except Exception as e:
            return False, f"Failed to launch browser: {e}"
