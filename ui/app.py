import asyncio
import os
import threading
import time
from queue import Empty, Queue
from tkinter import filedialog, messagebox

import customtkinter as ctk
import requests

# Configure customtkinter for proper scaling
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

from core.config_builder import TrafficConfigBuilder  # noqa: E402
from core.engine import AsyncTrafficEngine  # noqa: E402
from core.engine_factory import EngineFactory  # noqa: E402
from core.models import (  # noqa: E402
    EngineMode,
    ProxyCheckResult,
    ProxyConfig,
    TrafficStats,
)
from core.proxy_manager import ThreadedProxyManager  # noqa: E402
from core.session_manager import SessionManager  # noqa: E402
from core.settings_keys import SettingsKeys  # noqa: E402
from core.validators import DEFAULT_VALIDATORS  # noqa: E402

from .pages import (  # noqa: E402
    DashboardPage,
    MasterControlPage,
    ProxyManagerPage,
    SettingsPage,
    StressTestPage,
)
from .scaling import scaled  # noqa: E402
from .styles import COLORS  # noqa: E402
from .utils import Utils  # noqa: E402


class ModernTrafficBot(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.settings = Utils.load_settings()
        self.title("DARKMATTER-TB")
        self.geometry("1100x750")
        self.minsize(800, 500)  # Minimum window size for usability
        self.iconbitmap(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..",
                "resources",
                "favicon.ico",
            )
        )

        self.testing = False
        self.testing_paused = False
        self.running = False
        self.proxies = []
        self.checked_proxies = []  # Stores checked proxy results for persistence
        self.active_proxy_count = 0
        self.buffer = Queue()  # Thread-safe queue for proxy results
        self.stats = {"req": 0, "success": 0, "fail": 0}
        self.engine: AsyncTrafficEngine = None
        self.engine_thread: threading.Thread = None

        # Stress test state
        self.stress_running = False
        self.stress_paused = False
        self.stress_engine = None
        self.stress_thread: threading.Thread = None
        self.stress_stats = {
            "requests": 0,
            "success": 0,
            "failed": 0,
            "rps": 0.0,
            "latency": 0.0,
            "proxies_used": 0,
        }

        try:
            self.real_ip = requests.get("https://api.ipify.org", timeout=2).text
        except (requests.RequestException, OSError):
            self.real_ip = "0.0.0.0"

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.setup_sidebar()
        self.setup_pages()
        self.select_page("run")
        self.load_saved_proxies()  # Restore proxies from last session
        self.update_gui_loop()

        # Save proxies on window close
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_sidebar(self):
        self.sidebar = ctk.CTkFrame(
            self, width=scaled(180), corner_radius=0, fg_color=COLORS["nav"]
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(5, weight=1)
        self.sidebar.grid_propagate(False)  # Maintain width

        ctk.CTkLabel(
            self.sidebar,
            text="DARKMATTER",
            font=("Roboto", scaled(18), "bold"),
            text_color=COLORS["accent"],
        ).grid(row=0, column=0, padx=scaled(15), pady=(scaled(15), scaled(8)))

        self.nav_btns = {}
        for i, (key, text) in enumerate(
            [
                ("run", "🚀 Dashboard"),
                ("proxy", "🛡️ Proxy Manager"),
                ("stress", "💥 Stress Test"),
                ("master", "🌐 Master Control"),
                ("settings", "⚙️ Settings"),
            ]
        ):
            btn = ctk.CTkButton(
                self.sidebar,
                text=text,
                fg_color="transparent",
                text_color=COLORS["text_dim"],
                anchor="w",
                hover_color=COLORS["card"],
                height=scaled(36),
                font=("Roboto", scaled(12)),
                command=lambda k=key: self.select_page(k),
            )
            btn.grid(row=i + 1, column=0, sticky="ew", padx=scaled(8), pady=scaled(4))
            self.nav_btns[key] = btn

        ctk.CTkLabel(
            self.sidebar,
            text="v3.7.0",
            text_color=COLORS["text_dim"],
            font=("Roboto", scaled(10)),
        ).grid(row=7, column=0, pady=scaled(15))

    def setup_pages(self):
        self.pages = {}

        # Initialize page objects
        self.dashboard_page = DashboardPage(self)
        self.proxy_manager_page = ProxyManagerPage(self)
        self.stress_test_page = StressTestPage(self)
        self.master_control_page = MasterControlPage(self)
        self.settings_page = SettingsPage(self)

        # Create page frames and setup UI
        self.pages["run"] = ctk.CTkFrame(self, fg_color="transparent")
        self.dashboard_page.setup(self.pages["run"])
        self._bind_dashboard_widgets()

        self.pages["proxy"] = ctk.CTkFrame(self, fg_color="transparent")
        self.proxy_manager_page.setup(self.pages["proxy"])
        self._bind_proxy_manager_widgets()
        self.toggle_manual_target()  # Initialize manual target toggle state

        self.pages["stress"] = ctk.CTkFrame(self, fg_color="transparent")
        self.stress_test_page.setup(self.pages["stress"])
        self._bind_stress_test_widgets()

        self.pages["master"] = ctk.CTkFrame(self, fg_color="transparent")
        self.master_control_page.setup(self.pages["master"])

        self.pages["settings"] = ctk.CTkFrame(self, fg_color="transparent")
        self.settings_page.setup(self.pages["settings"])
        self._bind_settings_widgets()

    def _bind_dashboard_widgets(self):
        """Bind dashboard page widgets to self for backward compatibility."""
        p = self.dashboard_page
        self.lbl_stats = p.lbl_stats
        self.entry_url = p.entry_url
        self.mode_selector = p.mode_selector
        self.slider_threads = p.slider_threads
        self.slider_view_min = p.slider_view_min
        self.slider_view_max = p.slider_view_max
        self.slider_burst_size = p.slider_burst_size
        self.slider_burst_sleep = p.slider_burst_sleep
        self.lbl_threads = p.lbl_threads
        self.lbl_viewtime = p.lbl_viewtime
        self.lbl_burst = p.lbl_burst
        self.chk_burst_mode = p.chk_burst_mode
        self.btn_attack = p.btn_attack
        self.browser_stats_frame = p.browser_stats_frame
        self.lbl_browser_type = p.lbl_browser_type
        self.lbl_browser_contexts = p.lbl_browser_contexts
        self.lbl_captcha_stats = p.lbl_captcha_stats
        self.lbl_balance_2captcha = p.lbl_balance_2captcha
        self.lbl_balance_anticaptcha = p.lbl_balance_anticaptcha
        self.lbl_protection_stats = p.lbl_protection_stats
        self.lbl_protection_event = p.lbl_protection_event
        self.log_box = p.log_box

    def _bind_proxy_manager_widgets(self):
        """Bind proxy manager page widgets to self for backward compatibility."""
        p = self.proxy_manager_page
        self.proxy_grid = p.proxy_grid
        self.progress_bar = p.progress_bar
        self.lbl_loaded = p.lbl_loaded
        self.lbl_proto_counts = p.lbl_proto_counts
        self.lbl_bandwidth = p.lbl_bandwidth
        self.lbl_anon_counts = p.lbl_anon_counts
        self.entry_test_url = p.entry_test_url
        self.entry_timeout = p.entry_timeout
        self.entry_check_threads = p.entry_check_threads
        self.entry_scrape_threads = p.entry_scrape_threads
        self.entry_system_proxy = p.entry_system_proxy
        self.combo_system_proxy_proto = p.combo_system_proxy_proto
        self.chk_http = p.chk_http
        self.chk_socks4 = p.chk_socks4
        self.chk_socks5 = p.chk_socks5
        self.chk_hide_dead = p.chk_hide_dead
        self.chk_manual_target = p.chk_manual_target
        self.chk_proxy_for_scrape = p.chk_proxy_for_scrape
        self.chk_proxy_for_check = p.chk_proxy_for_check
        self.chk_export_protocol = p.chk_export_protocol
        self.btn_test = p.btn_test
        self.btn_pause = p.btn_pause
        self.btn_test_proxy = p.btn_test_proxy

    def _bind_stress_test_widgets(self):
        """Bind stress test page widgets to self for backward compatibility."""
        p = self.stress_test_page
        self.stress_stat_labels = p.stress_stat_labels
        self.stress_entry_url = p.stress_entry_url
        self.stress_attack_type = p.stress_attack_type
        self.stress_method = p.stress_method
        self.stress_proxy_count_label = p.stress_proxy_count_label
        self.stress_slider_threads = p.stress_slider_threads
        self.stress_slider_duration = p.stress_slider_duration
        self.stress_slider_rps = p.stress_slider_rps
        self.stress_lbl_threads = p.stress_lbl_threads
        self.stress_lbl_duration = p.stress_lbl_duration
        self.stress_lbl_rps = p.stress_lbl_rps
        self.btn_stress_start = p.btn_stress_start
        self.btn_stress_pause = p.btn_stress_pause
        self.btn_stress_reset = p.btn_stress_reset
        self.stress_log_box = p.stress_log_box

    def _bind_settings_widgets(self):
        """Bind settings page widgets to self for backward compatibility."""
        p = self.settings_page
        self.chk_headless = p.chk_headless
        self.chk_verify_ssl = p.chk_verify_ssl
        self.chk_session_persist = p.chk_session_persist
        self.combo_browser = p.combo_browser
        self.btn_browser_expand = p.btn_browser_expand
        self.browser_paths_frame = p.browser_paths_frame
        self.browser_paths_visible = p.browser_paths_visible
        self.entry_chrome_path = p.entry_chrome_path
        self.entry_chromium_path = p.entry_chromium_path
        self.entry_edge_path = p.entry_edge_path
        self.entry_brave_path = p.entry_brave_path
        self.entry_firefox_path = p.entry_firefox_path
        self.entry_other_path = p.entry_other_path
        self.slider_contexts = p.slider_contexts
        self.lbl_contexts = p.lbl_contexts
        self.chk_stealth = p.chk_stealth
        self.combo_captcha_primary = p.combo_captcha_primary
        self.chk_captcha_fallback = p.chk_captcha_fallback
        self.entry_2captcha_key = p.entry_2captcha_key
        self.entry_anticaptcha_key = p.entry_anticaptcha_key
        self.lbl_captcha_balance = p.lbl_captcha_balance
        self.chk_cloudflare = p.chk_cloudflare
        self.chk_akamai = p.chk_akamai
        self.chk_auto_captcha = p.chk_auto_captcha
        self.entry_cf_wait = p.entry_cf_wait
        self.combo_test_depth = p.combo_test_depth
        self.validator_checkboxes = p.validator_checkboxes

    def select_page(self, key):
        for _, p in self.pages.items():
            p.grid_forget()
        for _, b in self.nav_btns.items():
            b.configure(fg_color="transparent", text_color=COLORS["text_dim"])
        self.pages[key].grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.nav_btns[key].configure(fg_color=COLORS["card"], text_color=COLORS["text"])

    # ========== STRESS TEST PAGE METHODS ==========

    def stress_log(self, message: str):
        """Log a message to the stress test log box."""
        timestamp = time.strftime("%H:%M:%S")
        self.stress_log_box.insert("end", f"[{timestamp}] {message}\n")
        self.stress_log_box.see("end")

    def stress_log_safe(self, message: str):
        """Thread-safe stress log."""
        self.after(0, lambda: self.stress_log(message))

    def update_stress_proxy_count(self):
        """Update the HTTP proxy count label."""
        all_active = (
            self.proxy_grid.get_active_objects() if hasattr(self, "proxy_grid") else []
        )
        http_count = sum(1 for p in all_active if p.get("type", "").upper() == "HTTP")
        self.stress_proxy_count_label.configure(text=f"HTTP Proxies: {http_count:,}")

    def toggle_stress_test(self):
        """Start or stop the stress test."""
        if self.stress_running:
            self.stress_running = False
            self.btn_stress_start.configure(
                text="🚀 START STRESS TEST", fg_color=COLORS["success"]
            )
            if self.stress_engine:
                self.stress_engine.stop()
            self.stress_log("Stopping stress test...")
        else:
            # Confirmation dialog
            if not messagebox.askyesno(
                "Confirm Stress Test",
                "⚠️ AUTHORIZED TESTING ONLY\n\n"
                "This will send high-volume traffic to the target.\n"
                "Only use on servers you own or have permission to test.\n\n"
                "Continue?",
                icon="warning",
            ):
                return

            self.stress_running = True
            self.btn_stress_start.configure(
                text="⏹ STOP STRESS TEST", fg_color=COLORS["danger"]
            )

            # Start in separate thread
            self.stress_thread = threading.Thread(
                target=self.run_stress_engine, daemon=True
            )
            self.stress_thread.start()

    def toggle_stress_pause(self):
        """Pause or resume the stress test."""
        if not self.stress_running:
            return

        self.stress_paused = not self.stress_paused

        if self.stress_paused:
            self.btn_stress_pause.configure(text="▶ RESUME", fg_color=COLORS["success"])
            if self.stress_engine:
                self.stress_engine.pause()
            self.stress_log("Stress test PAUSED")
        else:
            self.btn_stress_pause.configure(text="⏸ PAUSE", fg_color=COLORS["warning"])
            if self.stress_engine:
                self.stress_engine.resume()
            self.stress_log("Stress test RESUMED")

    def reset_stress_stats(self):
        """Reset stress test statistics."""
        self.stress_stats = {
            "requests": 0,
            "success": 0,
            "failed": 0,
            "rps": 0.0,
            "latency": 0.0,
            "proxies_used": 0,
        }
        for key, lbl in self.stress_stat_labels.items():
            if key in ("rps", "latency"):
                lbl.configure(text="0.0")
            else:
                lbl.configure(text="0")
        self.stress_log("Statistics reset.")

    def run_stress_engine(self):
        """Run the stress test engine."""
        from core.stress_engine import (
            AttackType,
            RequestMethod,
            StressConfig,
            StressEngine,
        )

        target_url = self.stress_entry_url.get().strip()

        # Validate URL
        if not target_url:
            self.stress_log_safe("Error: Please enter a target URL")
            self.stress_running = False
            self.after(
                0,
                lambda: self.btn_stress_start.configure(
                    text="🚀 START STRESS TEST", fg_color=COLORS["success"]
                ),
            )
            return

        # Enforce HTTP only for stress testing
        if target_url.startswith("https://"):
            self.stress_log_safe(
                "Warning: HTTPS detected. HTTP proxies cannot tunnel HTTPS. Converting to HTTP..."
            )
            target_url = target_url.replace("https://", "http://", 1)
        elif not target_url.startswith("http://"):
            target_url = "http://" + target_url

        # Map attack type
        attack_type_map = {
            "HTTP Flood": AttackType.HTTP_FLOOD,
            "Slowloris": AttackType.SLOWLORIS,
            "RUDY": AttackType.RUDY,
            "Randomized": AttackType.RANDOMIZED,
        }
        attack_type = attack_type_map.get(
            self.stress_attack_type.get(), AttackType.HTTP_FLOOD
        )

        # Map method
        method_map = {
            "GET": RequestMethod.GET,
            "POST": RequestMethod.POST,
            "HEAD": RequestMethod.HEAD,
            "PUT": RequestMethod.PUT,
            "DELETE": RequestMethod.DELETE,
        }
        method = method_map.get(self.stress_method.get(), RequestMethod.GET)

        threads = Utils.safe_int(
            self.stress_slider_threads.get(), default=100, min_val=10, max_val=1000
        )
        duration = Utils.safe_int(
            self.stress_slider_duration.get(), default=60, min_val=10, max_val=300
        )
        rps_limit = Utils.safe_int(
            self.stress_slider_rps.get(), default=0, min_val=0, max_val=10000
        )

        # Get HTTP proxies only
        all_active = self.proxy_grid.get_active_objects()
        engine_proxies = []

        for p in all_active:
            if p.get("type", "").upper() == "HTTP":
                try:
                    engine_proxies.append(
                        ProxyConfig(host=p["ip"], port=int(p["port"]), protocol="http")
                    )
                except (ValueError, KeyError):
                    continue

        if not engine_proxies:
            self.stress_log_safe(
                "Error: No HTTP proxies available. Load and test proxies first."
            )
            self.stress_running = False
            self.after(
                0,
                lambda: self.btn_stress_start.configure(
                    text="🚀 START STRESS TEST", fg_color=COLORS["success"]
                ),
            )
            return

        self.stress_log_safe(
            f"Found {len(engine_proxies)} HTTP proxies for stress testing"
        )

        # Build config
        config = StressConfig(
            target_url=target_url,
            attack_type=attack_type,
            method=method,
            threads=threads,
            duration_seconds=duration,
            rps_limit=rps_limit,
        )

        # Create and run engine
        self.stress_engine = StressEngine(
            config=config,
            proxies=engine_proxies,
            on_stats_update=self.on_stress_stats_update,
            on_log=self.stress_log_safe,
        )

        # Run async loop
        asyncio.run(self.stress_engine.run())

        self.stress_running = False
        self.after(
            0,
            lambda: self.btn_stress_start.configure(
                text="🚀 START STRESS TEST", fg_color=COLORS["success"]
            ),
        )
        self.stress_log_safe("Stress test completed.")

    def on_stress_stats_update(self, stats):
        """Callback for stress engine stats updates."""

        def update_on_main():
            self.stress_stat_labels["requests"].configure(
                text=f"{stats.requests_sent:,}"
            )
            self.stress_stat_labels["success"].configure(
                text=f"{stats.requests_success:,}"
            )
            self.stress_stat_labels["failed"].configure(
                text=f"{stats.requests_failed:,}"
            )
            self.stress_stat_labels["rps"].configure(text=f"{stats.current_rps:.1f}")
            self.stress_stat_labels["latency"].configure(
                text=f"{stats.avg_latency_ms:.0f}ms"
            )
            self.stress_stat_labels["proxies"].configure(text=f"{stats.proxies_used:,}")

        self.after(0, update_on_main)

    # ========== SETTINGS PAGE METHODS ==========

    def browse_browser_path(self, entry_widget):
        """Open file dialog to select browser executable for a specific entry."""
        path = filedialog.askopenfilename(
            title="Select Browser Executable",
            filetypes=[("Executable", "*.exe"), ("All Files", "*.*")],
        )
        if path:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, path)
            self.log(f"Browser path set: {path}")

    def detect_all_browsers(self):
        """Auto-detect all installed browsers and populate paths."""
        from core.browser_manager import BrowserManager

        browsers = BrowserManager.detect_browsers()

        if not browsers:
            self.log("No browsers detected.")
            messagebox.showwarning(
                "Browser Detection",
                "No browsers found.\n\nPlease install Chrome, Chromium, Edge, Brave, or Firefox,\nor run: playwright install chromium",
            )
            return

        # Map browser names to entry widgets
        entry_map = {
            "Chrome": self.entry_chrome_path,
            "Chromium": self.entry_chromium_path,
            "Edge": self.entry_edge_path,
            "Brave": self.entry_brave_path,
            "Firefox": self.entry_firefox_path,
        }

        detected_names = []
        for browser in browsers:
            if browser.name in entry_map:
                entry = entry_map[browser.name]
                entry.delete(0, "end")
                entry.insert(0, browser.path)
                detected_names.append(browser.name)

        # Show paths section
        if not self.browser_paths_visible:
            self.toggle_browser_paths()

        self.log(f"Detected browsers: {', '.join(detected_names)}")
        messagebox.showinfo(
            "Browser Detection",
            f"Found {len(browsers)} browser(s):\n\n"
            + "\n".join([f"• {b.name}: {b.path}" for b in browsers]),
        )

    def check_captcha_balance(self):
        """Check captcha service balance for all configured providers."""
        key_2cap = self.entry_2captcha_key.get().strip()
        key_anti = self.entry_anticaptcha_key.get().strip()

        if not key_2cap and not key_anti:
            self.lbl_captcha_balance.configure(text="Enter at least one API key")
            return

        self.lbl_captcha_balance.configure(text="Checking...")

        def _check():
            try:
                from core.captcha_manager import CaptchaManager
                from core.models import CaptchaConfig, CaptchaProvider

                config = CaptchaConfig(
                    twocaptcha_key=key_2cap,
                    anticaptcha_key=key_anti,
                    primary_provider=CaptchaProvider.AUTO,
                )

                manager = CaptchaManager(config)
                balances = asyncio.run(manager.get_balances())

                # Format balance display
                parts = []
                for name, bal in balances.items():
                    if bal >= 0:
                        parts.append(f"{name}: ${bal:.2f}")
                    else:
                        parts.append(f"{name}: error")

                balance_text = " | ".join(parts) if parts else "No balances"
                has_positive = any(b > 0 for b in balances.values())

                self.after(
                    0,
                    lambda: self.lbl_captcha_balance.configure(
                        text=balance_text,
                        text_color=(
                            COLORS["success"] if has_positive else COLORS["warning"]
                        ),
                    ),
                )
            except ImportError:
                self.after(
                    0,
                    lambda: self.lbl_captcha_balance.configure(
                        text="aiohttp not installed", text_color=COLORS["danger"]
                    ),
                )
            except Exception as e:
                self.after(
                    0,
                    lambda err=e: self.lbl_captcha_balance.configure(
                        text=f"Balance: Error - {err}"
                    ),
                )

        threading.Thread(target=_check, daemon=True).start()

    def log(self, msg):
        """Log a message to the activity log with auto-scroll."""
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log_box.configure(state="disabled")
        # Schedule see() after GUI updates to ensure proper scroll
        self.log_box.after(10, lambda: self.log_box.see("end"))

    def log_safe(self, msg):
        """Thread-safe logging - use this when calling from worker threads."""
        self.after(0, lambda: self.log(msg))

    def load_proxy_file(self):
        f = filedialog.askopenfilename()
        if f:
            try:
                self.proxies = []
                self.buffer = Queue()  # Reset with fresh queue
                self.proxy_grid.clear()

                with open(f) as file:
                    for line in file:
                        line = line.strip()
                        if not line:
                            continue
                        # Normalize: Add http:// if no protocol specified (standardizes for dedup)
                        if "://" not in line:
                            line = "http://" + line
                        self.proxies.append(line)

                self.proxies = Utils.deduplicate_proxies(self.proxies)

                self.update_proxy_stats()
                self.log(
                    f"Cleared previous data. Loaded {len(self.proxies)} unique proxies."
                )
            except (OSError, UnicodeDecodeError) as e:
                self.log(f"Error loading proxy file: {e}")

    def import_from_clipboard(self):
        """Import proxies from clipboard (one per line, IP:PORT format)."""
        try:
            clipboard_text = self.clipboard_get()
        except Exception:
            return self.log("Clipboard is empty or unavailable.")

        if not clipboard_text or not clipboard_text.strip():
            return self.log("Clipboard is empty.")

        # Parse lines - supports IP:PORT or protocol://IP:PORT format
        lines = clipboard_text.strip().split("\n")
        new_proxies = []

        # Build set of existing proxies to skip duplicates
        existing_keys = set()
        for p in self.checked_proxies:
            existing_keys.add(f"{p.get('host', '')}:{p.get('port', '')}")
        for p in self.proxy_grid.data:
            existing_keys.add(f"{p.get('ip', '')}:{p.get('port', '')}")

        added = 0
        skipped = 0
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Normalize: Add http:// if no protocol specified
            if "://" not in line:
                line = "http://" + line

            # Extract host:port for dedup check
            try:
                if "://" in line:
                    addr = line.split("://", 1)[1]
                else:
                    addr = line
                if "@" in addr:
                    addr = addr.split("@", 1)[1]

                if addr in existing_keys:
                    skipped += 1
                    continue

                new_proxies.append(line)
                existing_keys.add(addr)
                added += 1
            except (ValueError, IndexError):
                new_proxies.append(line)
                added += 1

        if new_proxies:
            self.proxies.extend(new_proxies)
            self.proxies = Utils.deduplicate_proxies(self.proxies)
            self.update_proxy_stats()

        msg = f"Clipboard: Added {added} proxies"
        if skipped > 0:
            msg += f", skipped {skipped} duplicates"
        self.log(msg)

    def export_proxies(self, filter_type: str = "all"):
        """
        Export active proxies to files, filtered by type.

        Args:
            filter_type: "all", "http", "https", or "socks"
        """
        active_objs = self.proxy_grid.get_active_objects()

        if not active_objs:
            return self.log("No active proxies to export.")

        # Check if export folder is set, if not prompt user
        export_folder = self.settings.get("export_folder", "")
        if not export_folder or not os.path.exists(export_folder):
            export_folder = filedialog.askdirectory(
                title="Select Export Folder",
                initialdir=os.path.join(os.getcwd(), "resources"),
            )
            if not export_folder:
                return self.log("Export cancelled - no folder selected.")

            # Save the selection to settings
            self.settings["export_folder"] = export_folder
            Utils.save_settings(self.settings)
            self.log(f"Export folder set to: {export_folder}")

        # Check if protocol prefix should be included
        include_protocol = self.chk_export_protocol.get()
        self.settings["export_with_protocol"] = include_protocol
        Utils.save_settings(self.settings)

        # Categorize proxies
        http_list = []
        https_list = []
        socks_list = []

        for p in active_objs:
            p_type = p.get("type", "").upper()
            p_str = f"{p['ip']}:{p['port']}"

            if "SOCKS" in p_type:
                if include_protocol:
                    socks_list.append(
                        f"socks5://{p_str}" if "5" in p_type else f"socks4://{p_str}"
                    )
                else:
                    socks_list.append(p_str)
            elif p_type == "HTTPS":
                if include_protocol:
                    https_list.append(f"https://{p_str}")
                else:
                    https_list.append(p_str)
            else:
                if include_protocol:
                    http_list.append(f"http://{p_str}")
                else:
                    http_list.append(p_str)

        exported_count = 0
        try:
            if filter_type == "all":
                # Export all to separate files
                if http_list:
                    with open(os.path.join(export_folder, "http.txt"), "w") as f:
                        f.write("\n".join(http_list))
                    exported_count += len(http_list)
                if https_list:
                    with open(os.path.join(export_folder, "https.txt"), "w") as f:
                        f.write("\n".join(https_list))
                    exported_count += len(https_list)
                if socks_list:
                    with open(os.path.join(export_folder, "socks.txt"), "w") as f:
                        f.write("\n".join(socks_list))
                    exported_count += len(socks_list)
                # Also export combined file
                all_list = http_list + https_list + socks_list
                if all_list:
                    with open(os.path.join(export_folder, "all_proxies.txt"), "w") as f:
                        f.write("\n".join(all_list))
                self.log(
                    f"Exported All: {len(http_list)} HTTP, {len(https_list)} HTTPS, {len(socks_list)} SOCKS to {export_folder}"
                )

            elif filter_type == "http":
                if not http_list:
                    return self.log("No HTTP proxies to export.")
                with open(os.path.join(export_folder, "http.txt"), "w") as f:
                    f.write("\n".join(http_list))
                self.log(
                    f"Exported {len(http_list)} HTTP proxies to {export_folder}/http.txt"
                )

            elif filter_type == "https":
                if not https_list:
                    return self.log("No HTTPS proxies to export.")
                with open(os.path.join(export_folder, "https.txt"), "w") as f:
                    f.write("\n".join(https_list))
                self.log(
                    f"Exported {len(https_list)} HTTPS proxies to {export_folder}/https.txt"
                )

            elif filter_type == "socks":
                if not socks_list:
                    return self.log("No SOCKS proxies to export.")
                with open(os.path.join(export_folder, "socks.txt"), "w") as f:
                    f.write("\n".join(socks_list))
                self.log(
                    f"Exported {len(socks_list)} SOCKS proxies to {export_folder}/socks.txt"
                )

        except Exception as e:
            self.log(f"Export Error: {e}")

    def load_saved_proxies(self):
        """Load proxies saved from previous session."""
        saved = Utils.load_proxies()
        if not saved:
            return

        # Populate checked_proxies list and display in grid
        self.checked_proxies = saved
        active_count = 0

        for p in saved:
            # Only show active proxies
            if p.get("status") == "Active":
                active_count += 1
                item = {
                    "ip": p.get("host", ""),
                    "port": str(p.get("port", "")),
                    "type": p.get("type", ""),
                    "country": p.get("country", ""),
                    "country_code": p.get("country_code", ""),
                    "city": p.get("city", ""),
                    "status": p.get("status", "Unknown"),
                    "speed": p.get("speed", 0),
                    "anonymity": p.get("anonymity", "Unknown"),
                }
                self.proxy_grid.add(item)

            # Also rebuild self.proxies string list for campaigns
            host = p.get("host", "")
            port = p.get("port", "")
            protocol = p.get("protocol", "http")
            if host and port:
                self.proxies.append(f"{protocol}://{host}:{port}")

        if active_count > 0:
            self.update_proxy_stats()
            self.log(f"Restored {active_count} active proxies from last session.")

    def save_checked_proxies(self):
        """Save current checked proxies to file for persistence."""
        if not self.checked_proxies:
            return
        # Only save active proxies
        active = [p for p in self.checked_proxies if p.get("status") == "Active"]
        if active:
            Utils.save_proxies(active)
            self.log(f"Saved {len(active)} active proxies.")

    def clear_proxies(self):
        """Clear all proxies from memory and delete saved file."""
        self.proxies = []
        self.checked_proxies = []
        self.proxy_grid.clear()
        Utils.clear_saved_proxies()
        self.update_proxy_stats()
        self.log("All proxies cleared.")

    def clear_dead_proxies(self):
        """Clear only dead proxies from memory and grid, keeping active ones."""
        # Count before clearing
        total_before = len(self.proxy_grid.data)

        # Filter out dead proxies from the grid data
        active_data = [p for p in self.proxy_grid.data if p.get("status") == "Active"]

        # Filter checked_proxies list
        self.checked_proxies = [
            p for p in self.checked_proxies if p.get("status") == "Active"
        ]

        # Clear and repopulate grid with only active proxies
        self.proxy_grid.clear()
        for proxy in active_data:
            self.proxy_grid.add(proxy)
        self.proxy_grid.flush()

        # Update saved proxies file with only active ones
        if active_data:
            Utils.save_proxies(active_data)
        else:
            Utils.clear_saved_proxies()

        dead_count = total_before - len(active_data)
        self.update_proxy_stats()
        self.log(
            f"Cleared {dead_count} dead proxies. {len(active_data)} active proxies remaining."
        )

    def on_closing(self):
        """Handle window close - save proxies and cleanup."""
        # Stop any running operations
        self.testing = False
        self.running = False
        if self.engine:
            self.engine.stop()

        # Stop stress test if running
        self.stress_running = False
        if self.stress_engine:
            self.stress_engine.stop()

        # Save proxies before exit
        if self.checked_proxies:
            self.save_checked_proxies()

        # Also save any proxies currently in the grid
        grid_proxies = self.proxy_grid.get_active_objects()
        if grid_proxies and not self.checked_proxies:
            Utils.save_proxies(grid_proxies)

        # Stop master server if running
        if hasattr(self, "master_control_page"):
            self.master_control_page.cleanup()

        self.destroy()

    def run_scraper(self):
        scrape_threads = Utils.safe_int(
            self.entry_scrape_threads.get(), default=20, min_val=1, max_val=100
        )

        system_proxy = self.entry_system_proxy.get().strip()
        proto = self.combo_system_proxy_proto.get()
        use_for_scrape = self.chk_proxy_for_scrape.get()

        if use_for_scrape and system_proxy:
            # If no scheme is provided, prepend the selected protocol
            if "://" not in system_proxy:
                system_proxy = f"{proto}://{system_proxy}"
        else:
            system_proxy = None

        protos = []
        if self.chk_http.get():
            protos.append("http")
        if self.chk_socks4.get():
            protos.append("socks4")
        if self.chk_socks5.get():
            protos.append("socks5")

        # Resolve sources file path relative to app directory
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sources_file = os.path.join(app_dir, self.settings["sources"])

        # Ensure sources file exists with defaults
        if not os.path.exists(sources_file):
            os.makedirs(os.path.dirname(sources_file), exist_ok=True)
            with open(sources_file, "w") as f:
                f.write(
                    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt\n"
                )
                f.write(
                    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt\n"
                )
                f.write(
                    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http,socks4,socks5&timeout=10000&country=all\n"
                )

        def _job():
            self.log_safe(
                f"Scraping started (Async) using proxy: {system_proxy if system_proxy else 'Direct'}..."
            )
            try:
                with open(sources_file) as f:
                    urls = [
                        line.strip()
                        for line in f
                        if line.strip() and not line.startswith("#")
                    ]

                manager = ThreadedProxyManager()

                # Bandwidth tracking
                total_bytes = 0
                last_time = time.time()

                def on_scrape_progress(bytes_count):
                    nonlocal total_bytes, last_time
                    total_bytes += bytes_count

                    now = time.time()
                    delta = now - last_time
                    if delta >= 1.0:
                        # Mbps = (bytes * 8) / 1024 / 1024 / delta
                        # We calculate usage over the LAST delta interval for "current speed"?
                        # Or cumulative average? "Current speed" is better.
                        # But here total_bytes is cumulative.
                        # I need diff.
                        pass  # Logic inside ThreadedProxyManager returns bytes per call? Yes.

                # Improved bandwidth tracking with closure state
                scrape_bytes_buffer = 0
                scrape_total_bytes = 0

                def on_progress_wrapper(b):
                    nonlocal scrape_bytes_buffer, scrape_total_bytes, last_time
                    scrape_bytes_buffer += b
                    scrape_total_bytes += b
                    now = time.time()
                    if now - last_time >= 1.0:
                        mbps = (
                            (scrape_bytes_buffer * 8) / 1024 / 1024 / (now - last_time)
                        )
                        total_mb = scrape_total_bytes / (1024 * 1024)
                        self.after(
                            0,
                            lambda m=mbps, t=total_mb: self.lbl_bandwidth.configure(
                                text=f"Scrape: {m:.2f} Mbps ({t:.1f} MB)"
                            ),
                        )
                        last_time = now
                        scrape_bytes_buffer = 0

                # Run threaded scraper
                results = manager.scrape(
                    urls,
                    protos,
                    max_threads=scrape_threads,
                    scraper_proxy=system_proxy,
                    on_progress=on_progress_wrapper,
                )

                # Convert back to string format for the UI list for now (or update UI to hold objects)
                # The UI currently expects simple strings in self.proxies
                found_strings = [p.to_curl_cffi_format() for p in results]

                # Build set of already-checked proxy keys (host:port) to exclude duplicates
                checked_keys = set()
                for p in self.checked_proxies:
                    key = f"{p.get('host', '')}:{p.get('port', '')}"
                    checked_keys.add(key)

                # Also include proxies already in the grid
                for p in self.proxy_grid.data:
                    key = f"{p.get('ip', '')}:{p.get('port', '')}"
                    checked_keys.add(key)

                # Filter out already-checked proxies from new scrape
                new_proxies = []
                skipped = 0
                for p_str in found_strings:
                    # Extract host:port from proxy string
                    try:
                        if "://" in p_str:
                            addr = p_str.split("://", 1)[1]
                        else:
                            addr = p_str
                        if "@" in addr:
                            addr = addr.split("@", 1)[1]
                        # addr is now host:port
                        if addr in checked_keys:
                            skipped += 1
                            continue
                        new_proxies.append(p_str)
                    except (ValueError, IndexError):
                        new_proxies.append(p_str)

                if skipped > 0:
                    self.log_safe(f"Skipped {skipped} already-checked proxies.")

                self.proxies.extend(new_proxies)
                self.proxies = Utils.deduplicate_proxies(self.proxies)

                self.after(0, self.update_proxy_stats)
                self.log_safe(f"Scrape complete. Found {len(results)} proxies.")

                # Show notification
                total = len(self.proxies)
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Scrape Complete",
                        f"Found {len(results)} new proxies.\nTotal proxies loaded: {total}",
                    ),
                )
            except Exception as e:
                self.log_safe(f"Scrape Error: {e}")

        threading.Thread(target=_job, daemon=True).start()

    def update_proxy_stats(self):
        total = len(self.proxies)
        self.lbl_loaded.configure(text=f"Total: {total}")

        # Single-pass stats collection (more efficient than separate calls)
        counts, anon_counts = self.proxy_grid.get_all_stats()
        self.lbl_proto_counts.configure(
            text=f"HTTP: {counts['HTTP']} | HTTPS: {counts['HTTPS']} | SOCKS4: {counts['SOCKS4']} | SOCKS5: {counts['SOCKS5']}"
        )
        self.lbl_anon_counts.configure(
            text=f"Elite: {anon_counts['Elite']} | Anonymous: {anon_counts['Anonymous']} | Transparent: {anon_counts['Transparent']} | Unknown: {anon_counts['Unknown']}"
        )

        # Update stress test HTTP proxy count
        if hasattr(self, "stress_proxy_count_label"):
            self.stress_proxy_count_label.configure(
                text=f"HTTP Proxies: {counts['HTTP']:,}"
            )

    def toggle_manual_target(self):
        """Toggle between manual test URL and validators-based testing."""
        if self.chk_manual_target.get():
            self.entry_test_url.configure(state="normal", fg_color=COLORS["card"])
        else:
            self.entry_test_url.configure(state="disabled", fg_color=COLORS["nav"])

    def test_system_proxy(self):
        system_proxy = self.entry_system_proxy.get().strip()
        proto = self.combo_system_proxy_proto.get()
        if not system_proxy:
            return self.log("Enter a proxy first.")

        if "://" not in system_proxy:
            system_proxy = f"{proto}://{system_proxy}"

        self.btn_test_proxy.configure(
            text="...", state="disabled", fg_color=COLORS["warning"]
        )

        def _test():
            self.log(f"Testing system proxy: {system_proxy}...")
            try:
                proxies = {"http": system_proxy, "https": system_proxy}
                r = requests.get(
                    "https://api.ipify.org?format=json", proxies=proxies, timeout=10
                )
                if r.status_code == 200:
                    self.log(f"System Proxy OK! Exit IP: {r.json().get('ip')}")
                    self.after(
                        0,
                        lambda: self.btn_test_proxy.configure(
                            text="OK", fg_color=COLORS["success"]
                        ),
                    )
                else:
                    self.log(f"System Proxy Failed: HTTP {r.status_code}")
                    self.after(
                        0,
                        lambda: self.btn_test_proxy.configure(
                            text="FAIL", fg_color=COLORS["danger"]
                        ),
                    )
            except Exception as e:
                self.log(f"System Proxy Error: {e}")
                self.after(
                    0,
                    lambda: self.btn_test_proxy.configure(
                        text="ERR", fg_color=COLORS["danger"]
                    ),
                )

            # Reset button after 2 seconds
            def reset():
                self.btn_test_proxy.configure(
                    text="TEST", state="normal", fg_color=COLORS["accent"]
                )

            self.after(2000, reset)

        threading.Thread(target=_test, daemon=True).start()

    def toggle_pause_test(self):
        if not self.testing:
            return
        self.testing_paused = not self.testing_paused
        if self.testing_paused:
            self.btn_pause.configure(text="▶ RESUME", fg_color=COLORS["success"])
            self.log(
                "Testing PAUSED - You can change settings now. Click RESUME to continue."
            )
        else:
            self.btn_pause.configure(text="⏸ PAUSE", fg_color=COLORS["warning"])
            self.log("Testing RESUMED.")

    def toggle_test(self):
        if self.testing:
            self.testing = False
            self.testing_paused = False
            self.btn_test.configure(text="TEST ALL", fg_color=COLORS["success"])
            self.btn_pause.configure(
                state="disabled", text="⏸ PAUSE", fg_color=COLORS["warning"]
            )
            # Save proxies when user stops testing
            self.save_checked_proxies()
            self.log("Saved checked proxies.")
        else:
            if not self.proxies:
                return self.log("Load proxies first.")
            self.testing = True
            self.testing_paused = False
            self.btn_test.configure(text="STOP", fg_color=COLORS["danger"])
            self.btn_pause.configure(
                state="normal", text="⏸ PAUSE", fg_color=COLORS["warning"]
            )

            self.proxy_grid.clear()
            self.checked_proxies = []  # Clear for new test run
            threading.Thread(target=self.tester_thread, daemon=True).start()

    def tester_thread(self):
        # Progress bar is always visible (pinned), just reset to start
        self.after(0, lambda: self.progress_bar.set(0))
        try:
            use_manual_target = bool(self.chk_manual_target.get())

            # Get enabled validators from settings (needed early for URL determination)
            validators_enabled = self.settings.get("validators_enabled", {})
            active_validators = []
            for v in DEFAULT_VALIDATORS:
                if validators_enabled.get(v.name, v.enabled):
                    v.enabled = True
                    active_validators.append(v)
                else:
                    v.enabled = False

            # Determine test URL based on mode
            if use_manual_target:
                url = self.entry_test_url.get().strip()
                if not Utils.validate_url(url):
                    self.log_safe(
                        "Invalid test URL. Must start with http:// or https://"
                    )
                    self.testing = False
                    self.after(0, lambda: self.progress_bar.set(0))
                    self.after(
                        0,
                        lambda: self.btn_test.configure(
                            text="TEST ALL", fg_color=COLORS["success"]
                        ),
                    )
                    return
                self.log_safe(f"Using manual target: {url}")
            else:
                # Use first enabled validator as test URL
                if not active_validators:
                    self.log_safe(
                        "No validators enabled! Enable at least one validator in Settings."
                    )
                    self.testing = False
                    self.after(0, lambda: self.progress_bar.set(0))
                    self.after(
                        0,
                        lambda: self.btn_test.configure(
                            text="TEST ALL", fg_color=COLORS["success"]
                        ),
                    )
                    return
                url = active_validators[0].url
                self.log_safe(
                    f"Using validators (primary: {active_validators[0].name})"
                )

            timeout_ms = Utils.safe_int(
                self.entry_timeout.get(), default=3000, min_val=100, max_val=30000
            )
            check_threads = Utils.safe_int(
                self.entry_check_threads.get(), default=50, min_val=1, max_val=10000
            )
            hide_dead = self.chk_hide_dead.get()

            # Check if system proxy should be used for checking
            use_proxy_for_check = self.chk_proxy_for_check.get()
            system_proxy = (
                self.entry_system_proxy.get().strip() if use_proxy_for_check else None
            )
            if system_proxy:
                proto = self.combo_system_proxy_proto.get()
                if "://" not in system_proxy:
                    system_proxy = f"{proto}://{system_proxy}"
                self.log_safe(f"Using system proxy for checking: {system_proxy}")
                # Note: Full proxy chaining (hiding IP from proxy operators) requires SOCKS5 tunneling
                # Currently, this routes initial connection through system proxy

            # Prepare ProxyConfig objects from self.proxies (strings)
            # self.proxies contains strings like "http://1.2.3.4:80" or just "1.2.3.4:80"
            check_configs = []
            allowed_protos = []
            if self.chk_http.get():
                allowed_protos.append("http")
            if self.chk_socks4.get():
                allowed_protos.append("socks4")
            if self.chk_socks5.get():
                allowed_protos.append("socks5")

            for p_str in self.proxies:
                try:
                    if "://" in p_str:
                        parts = p_str.split("://")
                        scheme = parts[0].lower()
                        addr = parts[1]

                        # Treat https as http for validation against allowed_protos
                        check_scheme = "http" if scheme == "https" else scheme

                        if check_scheme not in allowed_protos:
                            continue
                    else:
                        # Ambiguous proxy, try all allowed protocols?
                        # Or default to HTTP. For checking, we usually want to know what it is.
                        # The old logic checked all allowed.
                        addr = p_str
                        scheme = "ambiguous"

                    if ":" in addr:
                        host, port = addr.split(":")[:2]
                        port = int(port)

                        if scheme == "ambiguous":
                            for proto in allowed_protos:
                                check_configs.append(
                                    ProxyConfig(host=host, port=port, protocol=proto)
                                )
                        else:
                            # Map https -> http for config
                            protocol = "http" if scheme == "https" else scheme
                            check_configs.append(
                                ProxyConfig(host=host, port=port, protocol=protocol)
                            )
                except (ValueError, IndexError, AttributeError):
                    continue  # Skip malformed proxy strings

        except Exception as e:
            self.log_safe(f"Config Error: {e}")
            return

        self.log_safe(f"Testing {len(check_configs)} proxies (Threaded/TLS)...")

        manager = ThreadedProxyManager()

        last_save_count = 0  # Track when we last saved
        last_save_time = time.time()  # Time-based save throttling
        last_ui_update = time.time()  # Throttle UI updates
        import threading as _threading

        ui_lock = _threading.Lock()  # Prevent concurrent UI scheduling

        # Bandwidth tracking with actual bytes
        total_bytes = [0]  # Use list for mutable closure
        last_bytes = [0]
        last_bandwidth_time = [time.time()]

        # Scale progress update interval with thread count to prevent callback flooding
        # Higher threads = less frequent updates to avoid GUI freeze
        progress_interval = max(50, min(500, check_threads // 10))

        # We need a callback that is thread-safe
        def on_progress(res: ProxyCheckResult, idx, total):
            nonlocal last_save_count, last_save_time, last_ui_update
            if not self.testing:
                return  # Stop signal

            # Track actual bytes transferred
            total_bytes[0] += res.bytes_transferred

            # Store result for persistence (only active proxies)
            if res.status == "Active":
                proxy_data = {
                    "host": res.proxy.host,
                    "port": res.proxy.port,
                    "protocol": res.proxy.protocol,
                    "status": res.status,
                    "speed": res.speed,
                    "type": res.type,
                    "country": res.country,
                    "country_code": res.country_code,
                    "city": res.city,
                    "anonymity": res.anonymity,
                }
                self.checked_proxies.append(proxy_data)

                # Auto-save with time-based throttling to prevent file contention
                # Only save if: 30+ seconds since last save AND 100+ new proxies
                active_count = len(self.checked_proxies)
                time_since_save = time.time() - last_save_time
                if (active_count - last_save_count >= 100) and (time_since_save >= 30):
                    last_save_count = active_count
                    last_save_time = time.time()
                    self.save_checked_proxies()
                    self.log_safe(f"Auto-saved {active_count} proxies...")

            if hide_dead and res.status != "Active":
                pass
            else:
                item = {
                    "ip": res.proxy.host,
                    "port": str(res.proxy.port),
                    "type": res.type,
                    "country": res.country,
                    "country_code": res.country_code,
                    "city": res.city,
                    "status": res.status,
                    "speed": res.speed,
                    "anonymity": res.anonymity,
                }
                self.buffer.put(item)  # Thread-safe put

            # Throttled UI updates - time-based to prevent callback flooding
            # Only schedule new callbacks if 200ms+ since last update
            with ui_lock:
                now = time.time()
                should_update_ui = (now - last_ui_update >= 0.2) or idx == total

                if should_update_ui and (idx % progress_interval == 0 or idx == total):
                    delta = now - last_bandwidth_time[0]
                    if delta >= 0.5:  # Bandwidth calc every 500ms
                        # Calculate actual bandwidth from bytes transferred
                        bytes_diff = total_bytes[0] - last_bytes[0]
                        # Convert to Mbps: (bytes * 8 bits) / (1024 * 1024) / seconds
                        mbps = (bytes_diff * 8) / (1024 * 1024) / delta
                        # Also show total transferred
                        total_mb = total_bytes[0] / (1024 * 1024)
                        self.after(
                            0,
                            lambda m=mbps, t=total_mb: self.lbl_bandwidth.configure(
                                text=f"Traffic: {m:.2f} Mbps ({t:.1f} MB)"
                            ),
                        )
                        last_bandwidth_time[0] = now
                        last_bytes[0] = total_bytes[0]

                    # Single progress update
                    progress = idx / total
                    self.after(0, lambda p=progress: self.progress_bar.set(p))
                    last_ui_update = now

        test_depth = self.settings.get("validator_test_depth", "quick")

        # Run threaded check with validators
        manager.check_proxies(
            check_configs,
            url,
            timeout_ms,
            self.real_ip,
            on_progress,
            concurrency=check_threads,
            pause_checker=lambda: self.testing_paused,
            validators=active_validators if active_validators else None,
            test_depth=test_depth,
            system_proxy=system_proxy,
        )

        self.testing = False
        self.after(0, lambda: self.progress_bar.set(1.0))  # Show complete, then fade
        self.after(500, lambda: self.progress_bar.set(0))  # Reset after brief delay
        self.after(
            0,
            lambda: self.btn_test.configure(
                text="TEST ALL", fg_color=COLORS["success"]
            ),
        )
        self.after(
            0,
            lambda: self.btn_pause.configure(
                state="disabled", text="⏸ PAUSE", fg_color=COLORS["warning"]
            ),
        )

        # Save checked proxies for persistence
        self.save_checked_proxies()
        self.log_safe("Testing complete.")

    def toggle_attack(self):
        if self.running:
            self.running = False
            self.btn_attack.configure(text="START CAMPAIGN", fg_color=COLORS["success"])
            if self.engine:
                self.engine.stop()
            self.log("Stopping campaign...")
        else:
            self.running = True
            self.btn_attack.configure(text="STOP CAMPAIGN", fg_color=COLORS["danger"])

            # Start Async Engine in a separate thread
            self.engine_thread = threading.Thread(
                target=self.run_async_engine, daemon=True
            )
            self.engine_thread.start()

    def run_async_engine(self):
        url = self.entry_url.get().strip()

        # Validate URL
        if not Utils.validate_url(url):
            self.log_safe("Invalid URL. Must start with http:// or https://")
            self.running = False
            self.after(
                0,
                lambda: self.btn_attack.configure(
                    text="START CAMPAIGN", fg_color=COLORS["success"]
                ),
            )
            return

        threads = Utils.safe_int(
            self.slider_threads.get(), default=1, min_val=1, max_val=500
        )
        v_min = Utils.safe_int(
            self.slider_view_min.get(), default=5, min_val=1, max_val=300
        )
        v_max = Utils.safe_int(
            self.slider_view_max.get(), default=10, min_val=1, max_val=300
        )
        if v_min > v_max:
            v_min, v_max = v_max, v_min

        self.log(f"Starting Async Engine: {threads} threads on {url}")

        # Prepare Proxies
        all_active = self.proxy_grid.get_active_objects()
        allowed = []
        if self.chk_http.get():
            allowed.append("HTTP")
        if self.chk_http.get():
            allowed.append("HTTPS")
        if self.chk_socks4.get():
            allowed.append("SOCKS4")
        if self.chk_socks5.get():
            allowed.append("SOCKS5")

        engine_proxies = []
        for p in all_active:
            if any(a in p["type"] for a in allowed):
                # Convert grid dict to ProxyConfig
                # Grid item: {'ip': '1.2.3.4', 'port': '80', 'type': 'HTTP', ...}
                try:
                    proto = p["type"].lower()
                    if "socks4" in proto:
                        protocol = "socks4"
                    elif "socks5" in proto:
                        protocol = "socks5"
                    else:
                        protocol = "http"

                    engine_proxies.append(
                        ProxyConfig(
                            host=p["ip"], port=int(p["port"]), protocol=protocol
                        )
                    )
                except (ValueError, KeyError, TypeError):
                    continue  # Skip malformed proxy entries

        if not engine_proxies and all_active:
            self.log_safe("Warning: Proxies active but filtered by protocol.")
        elif not engine_proxies:
            self.log_safe("No active proxies found. Running direct.")

        self.active_proxy_count = len(engine_proxies)

        # Merge current UI values with persistent settings for config building
        runtime_settings = dict(self.settings)
        runtime_settings[SettingsKeys.THREADS] = threads
        runtime_settings[SettingsKeys.VIEWTIME_MIN] = v_min
        runtime_settings[SettingsKeys.VIEWTIME_MAX] = v_max
        runtime_settings[SettingsKeys.BURST_MODE] = bool(self.chk_burst_mode.get())
        runtime_settings[SettingsKeys.BURST_REQUESTS] = int(self.slider_burst_size.get())
        burst_sleep = int(self.slider_burst_sleep.get())
        runtime_settings[SettingsKeys.BURST_SLEEP_MIN] = max(1, burst_sleep // 2)
        runtime_settings[SettingsKeys.BURST_SLEEP_MAX] = burst_sleep

        # Build config using centralized builder (eliminates magic strings)
        config = TrafficConfigBuilder.from_settings(runtime_settings, url)

        # Create session manager if persistence is enabled
        session_manager = None
        if self.settings.get("session_persistence", False):
            session_manager = SessionManager()
            self.log_safe("Session persistence enabled - cookies will be saved across runs")

        # Create engine using factory pattern (handles fallback gracefully)
        self.engine = EngineFactory.create_engine(
            mode=config.engine_mode,
            config=config,
            proxies=engine_proxies,
            on_update=self.on_engine_update,
            on_log=self.log_safe,
            session_manager=session_manager,
        )

        # Log which engine was selected
        if config.engine_mode == EngineMode.BROWSER:
            self.log_safe("Starting Browser Engine (stealth mode)...")
        else:
            self.log_safe("Starting Fast Engine (curl)...")

        # Run Async Loop
        asyncio.run(self.engine.run())

        self.running = False
        self.after(
            0,
            lambda: self.btn_attack.configure(
                text="START CAMPAIGN", fg_color=COLORS["success"]
            ),
        )
        self.log_safe("Campaign finished.")

    def reset_stats(self):
        self.stats = {"req": 0, "success": 0, "fail": 0}
        self.active_proxy_count = 0
        self.lbl_stats["req"].configure(text="0")
        self.lbl_stats["success"].configure(text="0")
        self.lbl_stats["fail"].configure(text="0")
        self.log("Campaign statistics reset.")

    def on_engine_update(self, stats: TrafficStats):
        # Callback from async engine - schedule on main GUI thread for thread safety
        # Copy values to avoid race conditions (stats object may change before callback runs)
        req = stats.total_requests
        success = stats.success
        fail = stats.failed
        proxies = stats.active_proxies

        # Browser stats (browser mode only)
        browser_type = stats.browser_type
        active_contexts = stats.active_contexts
        contexts_total = stats.contexts_total

        # Captcha stats
        captcha_solved = stats.captcha_solved
        captcha_failed = stats.captcha_failed
        captcha_pending = stats.captcha_pending
        balance_2captcha = stats.captcha_balance_2captcha
        balance_anticaptcha = stats.captcha_balance_anticaptcha

        # Protection stats
        cf_detected = stats.cloudflare_detected
        cf_bypassed = stats.cloudflare_bypassed
        ak_detected = stats.akamai_detected
        ak_bypassed = stats.akamai_bypassed
        last_event = stats.last_protection_event

        def update_on_main_thread():
            # Core stats
            self.stats["req"] = req
            self.stats["success"] = success
            self.stats["fail"] = fail
            self.active_proxy_count = proxies

            # Browser stats card (browser mode only)
            if browser_type:
                self.lbl_browser_type.configure(text=browser_type)
            self.lbl_browser_contexts.configure(
                text=f"Contexts: {active_contexts}/{contexts_total}"
            )

            # Captcha stats card (solved / failed / pending)
            self.lbl_captcha_stats.configure(
                text=f"{captcha_solved} / {captcha_failed} / {captcha_pending}"
            )

            # Update individual balance labels
            if balance_2captcha >= 0:
                self.lbl_balance_2captcha.configure(
                    text=f"2Cap: ${balance_2captcha:.2f}"
                )
            if balance_anticaptcha >= 0:
                self.lbl_balance_anticaptcha.configure(
                    text=f"Anti: ${balance_anticaptcha:.2f}"
                )

            # Protection stats card (detected / bypassed)
            total_detected = cf_detected + ak_detected
            total_bypassed = cf_bypassed + ak_bypassed
            self.lbl_protection_stats.configure(
                text=f"{total_detected} / {total_bypassed}"
            )
            if last_event:
                # Truncate long event messages
                display_event = (
                    last_event[:30] + "..." if len(last_event) > 30 else last_event
                )
                self.lbl_protection_event.configure(text=display_event)

        self.after(0, update_on_main_thread)

    def save_cfg(self):
        try:
            target_url = self.entry_url.get().strip()
            test_url = self.entry_test_url.get().strip()

            # Validate URLs before saving
            if target_url and not Utils.validate_url(target_url):
                self.log("Warning: Target URL appears invalid")

            if test_url and not Utils.validate_url(test_url):
                self.log("Warning: Test URL appears invalid")

            self.settings["target_url"] = target_url
            self.settings["threads"] = Utils.safe_int(
                self.slider_threads.get(), default=5, min_val=1, max_val=500
            )
            self.settings["viewtime_min"] = Utils.safe_int(
                self.slider_view_min.get(), default=5, min_val=1, max_val=300
            )
            self.settings["viewtime_max"] = Utils.safe_int(
                self.slider_view_max.get(), default=10, min_val=1, max_val=300
            )
            # Burst mode settings
            self.settings["burst_mode"] = bool(self.chk_burst_mode.get())
            self.settings["burst_requests"] = Utils.safe_int(
                self.slider_burst_size.get(), default=10, min_val=5, max_val=50
            )
            self.settings["burst_sleep_max"] = Utils.safe_int(
                self.slider_burst_sleep.get(), default=5, min_val=1, max_val=30
            )
            self.settings["burst_sleep_min"] = max(
                1, self.settings["burst_sleep_max"] // 2
            )
            self.settings["proxy_test_url"] = test_url
            self.settings["proxy_timeout"] = Utils.safe_int(
                self.entry_timeout.get(), default=3000, min_val=100, max_val=30000
            )
            self.settings["proxy_check_threads"] = Utils.safe_int(
                self.entry_check_threads.get(), default=50, min_val=1, max_val=10000
            )
            self.settings["proxy_scrape_threads"] = Utils.safe_int(
                self.entry_scrape_threads.get(), default=20, min_val=1, max_val=100
            )
            self.settings["system_proxy"] = self.entry_system_proxy.get().strip()
            self.settings["system_proxy_protocol"] = self.combo_system_proxy_proto.get()
            self.settings["use_proxy_for_scrape"] = self.chk_proxy_for_scrape.get()
            self.settings["use_proxy_for_check"] = self.chk_proxy_for_check.get()
            self.settings["use_manual_target"] = self.chk_manual_target.get()
            self.settings["use_http"] = self.chk_http.get()
            self.settings["use_socks4"] = self.chk_socks4.get()
            self.settings["use_socks5"] = self.chk_socks5.get()
            self.settings["hide_dead"] = self.chk_hide_dead.get()
            self.settings["headless"] = self.chk_headless.get()
            self.settings["verify_ssl"] = self.chk_verify_ssl.get()
            self.settings["session_persistence"] = self.chk_session_persist.get()

            # Engine mode (from dashboard selector)
            mode_value = self.mode_selector.get()
            self.settings["engine_mode"] = (
                "browser" if "Browser" in mode_value else "curl"
            )

            # Browser settings - individual paths
            self.settings["browser_selected"] = self.combo_browser.get().lower()
            self.settings["browser_chrome_path"] = self.entry_chrome_path.get().strip()
            self.settings["browser_chromium_path"] = (
                self.entry_chromium_path.get().strip()
            )
            self.settings["browser_edge_path"] = self.entry_edge_path.get().strip()
            self.settings["browser_brave_path"] = self.entry_brave_path.get().strip()
            self.settings["browser_firefox_path"] = (
                self.entry_firefox_path.get().strip()
            )
            self.settings["browser_other_path"] = self.entry_other_path.get().strip()
            self.settings["browser_contexts"] = Utils.safe_int(
                self.slider_contexts.get(), default=5, min_val=1, max_val=10
            )
            self.settings["browser_stealth"] = self.chk_stealth.get()
            self.settings["browser_headless"] = self.chk_headless.get()

            # Captcha settings - dual provider support
            captcha_primary = self.combo_captcha_primary.get().lower()
            self.settings["captcha_primary"] = (
                "none" if captcha_primary == "none" else captcha_primary
            )
            self.settings["captcha_2captcha_key"] = (
                self.entry_2captcha_key.get().strip()
            )
            self.settings["captcha_anticaptcha_key"] = (
                self.entry_anticaptcha_key.get().strip()
            )
            self.settings["captcha_fallback_enabled"] = self.chk_captcha_fallback.get()

            # Protection bypass settings
            self.settings["cloudflare_bypass"] = self.chk_cloudflare.get()
            self.settings["akamai_bypass"] = self.chk_akamai.get()
            self.settings["auto_solve_captcha"] = self.chk_auto_captcha.get()
            self.settings["cloudflare_wait"] = Utils.safe_int(
                self.entry_cf_wait.get(), default=10, min_val=1, max_val=60
            )

            # Validator settings
            self.settings["validator_test_depth"] = self.combo_test_depth.get().lower()
            validators_enabled = {}
            for name, chk in self.validator_checkboxes.items():
                validators_enabled[name] = chk.get()
            self.settings["validators_enabled"] = validators_enabled

            Utils.save_settings(self.settings)
            self.log("Settings saved.")
        except Exception as e:
            self.log(f"Error saving settings: {e}")

    def update_gui_loop(self):
        # Drain up to 100 items from the thread-safe queue (batch processing)
        items_processed = 0
        while items_processed < 100:
            try:
                item = self.buffer.get_nowait()
                self.proxy_grid.add(item)  # Deferred - no draw yet
                items_processed += 1
            except Empty:
                break

        # Flush grid changes (single draw for all items added this cycle)
        if items_processed > 0:
            self.proxy_grid.flush()

        # Throttle stats update - only every 500ms to reduce iteration overhead
        if not hasattr(self, "_last_stats_update"):
            self._last_stats_update = 0
        now = time.time()
        if items_processed > 0 and (now - self._last_stats_update >= 0.5):
            self.update_proxy_stats()
            self._last_stats_update = now

        self.lbl_stats["req"].configure(text=str(self.stats["req"]))
        self.lbl_stats["success"].configure(text=str(self.stats["success"]))
        self.lbl_stats["fail"].configure(text=str(self.stats["fail"]))
        self.lbl_stats["proxies"].configure(text=str(self.active_proxy_count))

        self.after(100, self.update_gui_loop)
