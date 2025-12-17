import customtkinter as ctk
import threading
import time
import os
import asyncio
import requests
from queue import Queue, Empty
from tkinter import filedialog, messagebox
from core.models import (
    TrafficConfig, ProxyConfig, TrafficStats, ProxyCheckResult,
    EngineMode, BrowserConfig, BrowserSelection, CaptchaConfig, CaptchaProvider, ProtectionBypassConfig
)
from core.engine import AsyncTrafficEngine
from core.proxy_manager import ThreadedProxyManager
from core.validators import DEFAULT_VALIDATORS
from .utils import Utils
from .components import VirtualGrid
from .styles import COLORS

class ModernTrafficBot(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.settings = Utils.load_settings()
        self.title("DARKMATTER-TB")
        self.geometry("1100x750")
        self.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources", "favicon.ico"))

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
            "requests": 0, "success": 0, "failed": 0,
            "rps": 0.0, "latency": 0.0, "proxies_used": 0
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
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0, fg_color=COLORS["nav"])
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(4, weight=1)

        ctk.CTkLabel(self.sidebar, text="DARKMATTER", font=("Roboto", 20, "bold"), text_color=COLORS["accent"]).grid(
            row=0, column=0, padx=20, pady=(20, 10))

        self.nav_btns = {}
        for i, (key, text) in enumerate(
                [("run", "🚀 Dashboard"), ("proxy", "🛡️ Proxy Manager"), ("stress", "💥 Stress Test"), ("settings", "⚙️ Settings")]):
            btn = ctk.CTkButton(self.sidebar, text=text, fg_color="transparent", text_color=COLORS["text_dim"],
                                anchor="w", hover_color=COLORS["card"], height=40,
                                command=lambda k=key: self.select_page(k))
            btn.grid(row=i + 1, column=0, sticky="ew", padx=10, pady=5)
            self.nav_btns[key] = btn

        ctk.CTkLabel(self.sidebar, text="v3.1.2 Stats", text_color=COLORS["text_dim"], font=("Roboto", 10)).grid(row=6,
                                                                                                                 column=0,
                                                                                                                 pady=20)

    def setup_pages(self):
        self.pages = {}
        self.pages["run"] = ctk.CTkFrame(self, fg_color="transparent")
        self.setup_run_ui(self.pages["run"])
        self.pages["proxy"] = ctk.CTkFrame(self, fg_color="transparent")
        self.setup_proxy_ui(self.pages["proxy"])
        self.pages["stress"] = ctk.CTkFrame(self, fg_color="transparent")
        self.setup_stress_ui(self.pages["stress"])
        self.pages["settings"] = ctk.CTkFrame(self, fg_color="transparent")
        self.setup_settings_ui(self.pages["settings"])

    def select_page(self, key):
        for k, p in self.pages.items(): p.grid_forget()
        for k, b in self.nav_btns.items(): b.configure(fg_color="transparent", text_color=COLORS["text_dim"])
        self.pages[key].grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.nav_btns[key].configure(fg_color=COLORS["card"], text_color=COLORS["text"])

    def setup_run_ui(self, parent):
        # Use grid for scalable layout
        parent.grid_rowconfigure(3, weight=1)  # Activity log expands
        parent.grid_columnconfigure(0, weight=1)

        # Primary Stats Row - Request metrics
        stats_frame = ctk.CTkFrame(parent, fg_color="transparent")
        stats_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        stats_frame.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="stats")

        self.lbl_stats = {}
        stat_configs = [
            ("req", "Requests", COLORS["text"]),
            ("success", "Success", COLORS["success"]),
            ("fail", "Failed", COLORS["danger"]),
            ("proxies", "Proxies", COLORS["accent"])
        ]
        for col, (key, title, color) in enumerate(stat_configs):
            card = ctk.CTkFrame(stats_frame, fg_color=COLORS["card"])
            card.grid(row=0, column=col, sticky="nsew", padx=3, pady=2)
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(card, text=title, font=("Roboto", 10), text_color=COLORS["text_dim"]).pack(pady=(8, 2))
            lbl = ctk.CTkLabel(card, text="0", font=("Roboto", 22, "bold"), text_color=color)
            lbl.pack(pady=(0, 8))
            self.lbl_stats[key] = lbl

        # Configuration Card
        cfg_frame = ctk.CTkFrame(parent, fg_color=COLORS["card"])
        cfg_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(cfg_frame, text="Attack Configuration", font=("Roboto", 14, "bold")).pack(anchor="w", padx=20, pady=15)

        self.entry_url = ctk.CTkEntry(cfg_frame, placeholder_text="https://target.com", height=35)
        self.entry_url.pack(fill="x", padx=20, pady=(0, 10))
        self.entry_url.insert(0, self.settings["target_url"])

        # Engine Mode Selector
        mode_frame = ctk.CTkFrame(cfg_frame, fg_color="transparent")
        mode_frame.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(mode_frame, text="Engine:", font=("Roboto", 12)).pack(side="left", padx=(0, 10))

        self.mode_selector = ctk.CTkSegmentedButton(
            mode_frame,
            values=["Fast (curl)", "Browser (stealth)"],
            command=self.on_mode_change,
            font=("Roboto", 11),
            fg_color=COLORS["card"],
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
        )
        current_mode = self.settings.get("engine_mode", "curl")
        self.mode_selector.set("Fast (curl)" if current_mode == "curl" else "Browser (stealth)")
        self.mode_selector.pack(side="left", fill="x", expand=True)

        # Sliders using grid for proportional sizing
        slider_row = ctk.CTkFrame(cfg_frame, fg_color="transparent")
        slider_row.pack(fill="x", padx=15, pady=10)
        slider_row.grid_columnconfigure(0, weight=2)  # Threads gets 2/5
        slider_row.grid_columnconfigure(1, weight=3)  # Duration gets 3/5

        # Threads slider
        t_frame = ctk.CTkFrame(slider_row, fg_color="transparent")
        t_frame.grid(row=0, column=0, sticky="nsew", padx=5)

        self.lbl_threads = ctk.CTkLabel(t_frame, text=f"Threads: {self.settings.get('threads', 5)}")
        self.lbl_threads.pack(anchor="w")

        self.slider_threads = ctk.CTkSlider(t_frame, from_=1, to=100, number_of_steps=99,
                                            command=self.update_thread_lbl, button_color=COLORS["accent"], button_hover_color=COLORS["accent_hover"])
        self.slider_threads.set(self.settings.get("threads", 5))
        self.slider_threads.pack(fill="x", pady=5)

        # View duration sliders
        v_frame = ctk.CTkFrame(slider_row, fg_color="transparent")
        v_frame.grid(row=0, column=1, sticky="nsew", padx=5)

        self.lbl_viewtime = ctk.CTkLabel(v_frame,
                                         text=f"Duration: {self.settings.get('viewtime_min', 5)}s - {self.settings.get('viewtime_max', 10)}s")
        self.lbl_viewtime.pack(anchor="w")

        # Min/Max sliders in a sub-grid
        duration_sliders = ctk.CTkFrame(v_frame, fg_color="transparent")
        duration_sliders.pack(fill="x")
        duration_sliders.grid_columnconfigure((0, 1), weight=1)

        min_frame = ctk.CTkFrame(duration_sliders, fg_color="transparent")
        min_frame.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ctk.CTkLabel(min_frame, text="Min:", font=("Roboto", 10)).pack(anchor="w")
        self.slider_view_min = ctk.CTkSlider(min_frame, from_=1, to=60, number_of_steps=59, command=self.update_view_lbl, button_color=COLORS["accent"], button_hover_color=COLORS["accent_hover"])
        self.slider_view_min.set(self.settings.get("viewtime_min", 5))
        self.slider_view_min.pack(fill="x", pady=2)

        max_frame = ctk.CTkFrame(duration_sliders, fg_color="transparent")
        max_frame.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        ctk.CTkLabel(max_frame, text="Max:", font=("Roboto", 10)).pack(anchor="w")
        self.slider_view_max = ctk.CTkSlider(max_frame, from_=1, to=60, number_of_steps=59, command=self.update_view_lbl, button_color=COLORS["accent"], button_hover_color=COLORS["accent_hover"])
        self.slider_view_max.set(self.settings.get("viewtime_max", 10))
        self.slider_view_max.pack(fill="x", pady=2)

        # Button Row
        btn_row = ctk.CTkFrame(cfg_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=20)

        self.btn_attack = ctk.CTkButton(btn_row, text="START CAMPAIGN", height=45, fg_color=COLORS["success"],
                                        font=("Roboto", 14, "bold"), command=self.toggle_attack)
        self.btn_attack.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.btn_reset = ctk.CTkButton(btn_row, text="RESET", height=45, fg_color=COLORS["warning"],
                                       font=("Roboto", 12, "bold"), width=80, command=self.reset_stats)
        self.btn_reset.pack(side="right")

        # Browser Stats Panel (row 2) - shown only in browser mode, above activity log
        self.browser_stats_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.browser_stats_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.browser_stats_frame.grid_columnconfigure((0, 1, 2), weight=1, uniform="bstats")

        # Browser Info Card
        browser_card = ctk.CTkFrame(self.browser_stats_frame, fg_color=COLORS["card"])
        browser_card.grid(row=0, column=0, sticky="nsew", padx=3, pady=2)
        ctk.CTkLabel(browser_card, text="Browser", font=("Roboto", 10), text_color=COLORS["text_dim"]).pack(pady=(8, 2))
        self.lbl_browser_type = ctk.CTkLabel(browser_card, text="--", font=("Roboto", 16, "bold"), text_color=COLORS["accent"])
        self.lbl_browser_type.pack(pady=(0, 2))
        self.lbl_browser_contexts = ctk.CTkLabel(browser_card, text="Contexts: 0/0", font=("Roboto", 10), text_color=COLORS["text_dim"])
        self.lbl_browser_contexts.pack(pady=(0, 8))

        # Captcha Stats Card
        captcha_card = ctk.CTkFrame(self.browser_stats_frame, fg_color=COLORS["card"])
        captcha_card.grid(row=0, column=1, sticky="nsew", padx=3, pady=2)
        ctk.CTkLabel(captcha_card, text="Captcha (✓/✗/⋯)", font=("Roboto", 10), text_color=COLORS["text_dim"]).pack(pady=(8, 2))
        self.lbl_captcha_stats = ctk.CTkLabel(captcha_card, text="0 / 0 / 0", font=("Roboto", 16, "bold"), text_color=COLORS["success"])
        self.lbl_captcha_stats.pack(pady=(0, 4))

        # Separate balance labels for each provider
        balance_frame = ctk.CTkFrame(captcha_card, fg_color="transparent")
        balance_frame.pack(fill="x", padx=10, pady=(0, 8))
        balance_frame.grid_columnconfigure((0, 1), weight=1)

        self.lbl_balance_2captcha = ctk.CTkLabel(balance_frame, text="2Cap: --", font=("Roboto", 10), text_color=COLORS["text_dim"])
        self.lbl_balance_2captcha.grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.lbl_balance_anticaptcha = ctk.CTkLabel(balance_frame, text="Anti: --", font=("Roboto", 10), text_color=COLORS["text_dim"])
        self.lbl_balance_anticaptcha.grid(row=0, column=1, sticky="e", padx=(5, 0))

        # Protection Status Card
        protection_card = ctk.CTkFrame(self.browser_stats_frame, fg_color=COLORS["card"])
        protection_card.grid(row=0, column=2, sticky="nsew", padx=3, pady=2)
        ctk.CTkLabel(protection_card, text="Protection (det/byp)", font=("Roboto", 10), text_color=COLORS["text_dim"]).pack(pady=(8, 2))
        self.lbl_protection_stats = ctk.CTkLabel(protection_card, text="0 / 0", font=("Roboto", 16, "bold"), text_color=COLORS["warning"])
        self.lbl_protection_stats.pack(pady=(0, 2))
        self.lbl_protection_event = ctk.CTkLabel(protection_card, text="No events", font=("Roboto", 10), text_color=COLORS["text_dim"])
        self.lbl_protection_event.pack(pady=(0, 8))

        # Hide browser stats by default (shown when browser mode selected)
        self._update_browser_stats_visibility()

        # Activity Log (row 3) - expands to fill remaining space
        log_frame = ctk.CTkFrame(parent, fg_color="transparent")
        log_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 0))
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(log_frame, text="Activity Log", font=("Roboto", 11), text_color=COLORS["text_dim"]).grid(
            row=0, column=0, sticky="w", pady=(0, 4))
        self.log_box = ctk.CTkTextbox(log_frame, fg_color=COLORS["card"])
        self.log_box.grid(row=1, column=0, sticky="nsew")

    def update_thread_lbl(self, value):
        self.lbl_threads.configure(text=f"Threads: {int(value)}")

    def update_view_lbl(self, value):
        mn = int(self.slider_view_min.get())
        mx = int(self.slider_view_max.get())
        self.lbl_viewtime.configure(text=f"Duration: {mn}s - {mx}s")

    def on_mode_change(self, value):
        """Handle engine mode change."""
        is_browser = "Browser" in value
        self.settings["engine_mode"] = "browser" if is_browser else "curl"

        # Adjust thread slider limits based on mode
        if is_browser:
            # Browser mode: 1-10 contexts (RAM limited)
            self.slider_threads.configure(from_=1, to=10, number_of_steps=9)
            current = int(self.slider_threads.get())
            if current > 10:
                self.slider_threads.set(5)
                self.lbl_threads.configure(text="Threads: 5")
        else:
            # Curl mode: 1-100 threads
            self.slider_threads.configure(from_=1, to=100, number_of_steps=99)

        # Update browser stats visibility
        self._update_browser_stats_visibility()

        self.log(f"Engine mode: {'Browser (stealth)' if is_browser else 'Fast (curl)'}")

    def _update_browser_stats_visibility(self):
        """Show/hide browser stats row based on engine mode."""
        is_browser = self.settings.get("engine_mode", "curl") == "browser"
        if is_browser:
            self.browser_stats_frame.grid()
        else:
            self.browser_stats_frame.grid_remove()

    def setup_proxy_ui(self, parent):
        tools = ctk.CTkFrame(parent, fg_color=COLORS["card"])
        tools.pack(fill="x", pady=(0, 10))

        # Row 1: Actions & Protocol Checkboxes
        r1 = ctk.CTkFrame(tools, fg_color="transparent")
        r1.pack(fill="x", padx=10, pady=10)

        ctk.CTkButton(r1, text="Scrape New", width=100, command=self.run_scraper, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"]).pack(side="left", padx=5)
        ctk.CTkButton(r1, text="Load File", width=100, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], command=self.load_proxy_file).pack(
            side="left", padx=5)
        ctk.CTkButton(r1, text="Clipboard", width=80, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], command=self.import_from_clipboard).pack(
            side="left", padx=5)
        ctk.CTkButton(r1, text="Clear All", width=80, fg_color=COLORS["danger"], command=self.clear_proxies).pack(
            side="right", padx=5)
        ctk.CTkButton(r1, text="Export Active", width=100, fg_color="#F39C12", command=self.export_active).pack(
            side="right", padx=5)

        proto_frm = ctk.CTkFrame(tools, fg_color="transparent")
        proto_frm.pack(fill="x", padx=10, pady=5)

        self.chk_http = ctk.CTkCheckBox(proto_frm, text="HTTP/S", width=70, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        if self.settings.get("use_http", True): self.chk_http.select()
        self.chk_http.pack(side="left", padx=10)

        self.chk_socks4 = ctk.CTkCheckBox(proto_frm, text="SOCKS4", width=70, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        if self.settings.get("use_socks4", True): self.chk_socks4.select()
        self.chk_socks4.pack(side="left", padx=10)

        self.chk_socks5 = ctk.CTkCheckBox(proto_frm, text="SOCKS5", width=70, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        if self.settings.get("use_socks5", True): self.chk_socks5.select()
        self.chk_socks5.pack(side="left", padx=10)

        self.chk_hide_dead = ctk.CTkCheckBox(proto_frm, text="Hide Dead", width=70, fg_color=COLORS["danger"])
        if self.settings.get("hide_dead", True): self.chk_hide_dead.select()
        self.chk_hide_dead.pack(side="right", padx=10)

        r_counts = ctk.CTkFrame(tools, fg_color="transparent")
        r_counts.pack(fill="x", padx=10, pady=5)

        self.lbl_loaded = ctk.CTkLabel(r_counts, text="Total: 0", font=("Roboto", 12, "bold"))
        self.lbl_loaded.pack(side="left", padx=5)

        self.lbl_proto_counts = ctk.CTkLabel(r_counts, text="HTTP: 0 | HTTPS: 0 | SOCKS4: 0 | SOCKS5: 0",
                                             text_color=COLORS["text_dim"], font=("Roboto", 11))
        self.lbl_proto_counts.pack(side="right", padx=15)

        self.lbl_bandwidth = ctk.CTkLabel(r_counts, text="Traffic: 0.00 Mbps (0.0 MB)", text_color=COLORS["success"], font=("Roboto", 11, "bold"))
        self.lbl_bandwidth.pack(side="right", padx=5)

        # Anonymity counts row
        r_anon = ctk.CTkFrame(tools, fg_color="transparent")
        r_anon.pack(fill="x", padx=10, pady=2)

        ctk.CTkLabel(r_anon, text="Anonymity:", font=("Roboto", 11), text_color=COLORS["text_dim"]).pack(side="left", padx=5)
        self.lbl_anon_counts = ctk.CTkLabel(r_anon, text="Elite: 0 | Anonymous: 0 | Transparent: 0 | Unknown: 0",
                                             text_color=COLORS["text_dim"], font=("Roboto", 11))
        self.lbl_anon_counts.pack(side="left", padx=10)

        r2 = ctk.CTkFrame(tools, fg_color=COLORS["bg"])
        r2.pack(fill="x", padx=10, pady=(0, 10))

        # Left side - Test URL (flexible width)
        r2_left = ctk.CTkFrame(r2, fg_color="transparent")
        r2_left.pack(side="left", fill="x", expand=True, padx=5, pady=5)

        # Manual target checkbox - when unchecked, uses validators from settings
        self.chk_manual_target = ctk.CTkCheckBox(r2_left, text="Manual:", width=70,
                                                   fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                                                   command=self.toggle_manual_target)
        if self.settings.get("use_manual_target", True):
            self.chk_manual_target.select()
        self.chk_manual_target.pack(side="left", padx=(0, 2))

        self.entry_test_url = ctk.CTkEntry(r2_left, placeholder_text="Test URL (or use validators)")
        self.entry_test_url.insert(0, self.settings["proxy_test_url"])
        self.entry_test_url.pack(side="left", fill="x", expand=True, padx=(0, 5))

        ctk.CTkLabel(r2_left, text="Timeout:").pack(side="left", padx=2)
        self.entry_timeout = ctk.CTkEntry(r2_left, width=50)
        self.entry_timeout.insert(0, str(self.settings["proxy_timeout"]))
        self.entry_timeout.pack(side="left", padx=2)

        ctk.CTkLabel(r2_left, text="Threads:").pack(side="left", padx=(5, 2))
        self.entry_check_threads = ctk.CTkEntry(r2_left, width=40)
        self.entry_check_threads.insert(0, str(self.settings["proxy_check_threads"]))
        self.entry_check_threads.pack(side="left", padx=2)

        ctk.CTkLabel(r2_left, text="Scrape:").pack(side="left", padx=(5, 2))
        self.entry_scrape_threads = ctk.CTkEntry(r2_left, width=40)
        self.entry_scrape_threads.insert(0, str(self.settings["proxy_scrape_threads"]))
        self.entry_scrape_threads.pack(side="left", padx=2)

        # Right side - Buttons (fixed width)
        r2_right = ctk.CTkFrame(r2, fg_color="transparent")
        r2_right.pack(side="right", padx=5, pady=5)

        self.btn_pause = ctk.CTkButton(r2_right, text="⏸ PAUSE", width=80, fg_color=COLORS["warning"],
                                       command=self.toggle_pause_test, state="disabled")
        self.btn_pause.pack(side="left", padx=2)

        self.btn_test = ctk.CTkButton(r2_right, text="TEST ALL", width=80, fg_color=COLORS["success"],
                                      command=self.toggle_test)
        self.btn_test.pack(side="left", padx=2)

        r3 = ctk.CTkFrame(tools, fg_color=COLORS["bg"])
        r3.pack(fill="x", padx=10, pady=(0, 5))

        # Left side - Label and protocol combo (fixed)
        ctk.CTkLabel(r3, text="System Proxy:").pack(side="left", padx=5)

        self.combo_system_proxy_proto = ctk.CTkComboBox(r3, values=["http", "socks4", "socks5"], width=80)
        self.combo_system_proxy_proto.set(self.settings.get("system_proxy_protocol", "http"))
        self.combo_system_proxy_proto.pack(side="left", padx=2)

        # Right side - Buttons and checkboxes (fixed, pack first so they don't get clipped)
        self.btn_test_proxy = ctk.CTkButton(r3, text="TEST", width=50, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], command=self.test_system_proxy)
        self.btn_test_proxy.pack(side="right", padx=5)

        self.chk_proxy_for_check = ctk.CTkCheckBox(r3, text="Check", width=60, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        if self.settings.get("use_proxy_for_check", False): self.chk_proxy_for_check.select()
        self.chk_proxy_for_check.pack(side="right", padx=2)

        self.chk_proxy_for_scrape = ctk.CTkCheckBox(r3, text="Scrape", width=65, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        if self.settings.get("use_proxy_for_scrape", False): self.chk_proxy_for_scrape.select()
        self.chk_proxy_for_scrape.pack(side="right", padx=2)

        # Middle - Proxy entry (flexible, fills remaining space)
        self.entry_system_proxy = ctk.CTkEntry(r3, placeholder_text="user:pass@ip:port")
        self.entry_system_proxy.insert(0, self.settings.get("system_proxy", ""))
        self.entry_system_proxy.pack(side="left", fill="x", expand=True, padx=5)

        self.progress_bar = ctk.CTkProgressBar(parent, height=10)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", pady=(0, 5))
        self.progress_bar.pack_forget()

        self.proxy_grid = VirtualGrid(parent, columns=["Address", "Proto", "Country", "Status", "Ping", "Anon"])
        self.proxy_grid.pack(fill="both", expand=True)

        # Initialize manual target toggle state
        self.toggle_manual_target()

    def setup_stress_ui(self, parent):
        """Set up the Stress Test tab UI."""
        parent.grid_rowconfigure(3, weight=1)  # Log expands
        parent.grid_columnconfigure(0, weight=1)

        # Warning Banner
        warning_frame = ctk.CTkFrame(parent, fg_color="#8B0000")
        warning_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(
            warning_frame,
            text="⚠️  FOR AUTHORIZED SECURITY TESTING ONLY - TEST YOUR OWN SERVERS  ⚠️",
            font=("Roboto", 12, "bold"),
            text_color="white"
        ).pack(pady=8)

        # Stats Row
        stats_frame = ctk.CTkFrame(parent, fg_color="transparent")
        stats_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        stats_frame.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1, uniform="stress_stats")

        self.stress_stat_labels = {}
        stress_stat_configs = [
            ("requests", "Requests", COLORS["text"]),
            ("success", "Success", COLORS["success"]),
            ("failed", "Failed", COLORS["danger"]),
            ("rps", "RPS", COLORS["accent"]),
            ("latency", "Latency", COLORS["warning"]),
            ("proxies", "Proxies", COLORS["text"]),
        ]
        for col, (key, title, color) in enumerate(stress_stat_configs):
            card = ctk.CTkFrame(stats_frame, fg_color=COLORS["card"])
            card.grid(row=0, column=col, sticky="nsew", padx=2, pady=2)
            ctk.CTkLabel(card, text=title, font=("Roboto", 9), text_color=COLORS["text_dim"]).pack(pady=(6, 1))
            lbl = ctk.CTkLabel(card, text="0", font=("Roboto", 16, "bold"), text_color=color)
            lbl.pack(pady=(0, 6))
            self.stress_stat_labels[key] = lbl

        # Configuration Card
        cfg_frame = ctk.CTkFrame(parent, fg_color=COLORS["card"])
        cfg_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(cfg_frame, text="Stress Test Configuration", font=("Roboto", 14, "bold")).pack(anchor="w", padx=20, pady=15)

        # Target URL (HTTP only)
        target_row = ctk.CTkFrame(cfg_frame, fg_color="transparent")
        target_row.pack(fill="x", padx=20, pady=(0, 10))

        self.stress_entry_url = ctk.CTkEntry(target_row, placeholder_text="http://your-server.com/test", height=35)
        self.stress_entry_url.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkLabel(target_row, text="HTTP Only", font=("Roboto", 10), text_color=COLORS["warning"]).pack(side="right")

        # Attack Type & Method Row
        type_row = ctk.CTkFrame(cfg_frame, fg_color="transparent")
        type_row.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(type_row, text="Attack:", font=("Roboto", 12)).pack(side="left", padx=(0, 5))
        self.stress_attack_type = ctk.CTkComboBox(
            type_row,
            values=["HTTP Flood", "Slowloris", "RUDY", "Randomized"],
            width=130,
            state="readonly"
        )
        self.stress_attack_type.set("HTTP Flood")
        self.stress_attack_type.pack(side="left", padx=(0, 20))

        ctk.CTkLabel(type_row, text="Method:", font=("Roboto", 12)).pack(side="left", padx=(0, 5))
        self.stress_method = ctk.CTkComboBox(
            type_row,
            values=["GET", "POST", "HEAD", "PUT", "DELETE"],
            width=80,
            state="readonly"
        )
        self.stress_method.set("GET")
        self.stress_method.pack(side="left", padx=(0, 20))

        # HTTP Proxies count label
        self.stress_proxy_count_label = ctk.CTkLabel(
            type_row,
            text="HTTP Proxies: 0",
            font=("Roboto", 11),
            text_color=COLORS["accent"]
        )
        self.stress_proxy_count_label.pack(side="right")

        # Sliders Row
        slider_row = ctk.CTkFrame(cfg_frame, fg_color="transparent")
        slider_row.pack(fill="x", padx=15, pady=10)
        slider_row.grid_columnconfigure((0, 1, 2), weight=1)

        # Threads slider
        t_frame = ctk.CTkFrame(slider_row, fg_color="transparent")
        t_frame.grid(row=0, column=0, sticky="nsew", padx=5)
        self.stress_lbl_threads = ctk.CTkLabel(t_frame, text="Threads: 100")
        self.stress_lbl_threads.pack(anchor="w")
        self.stress_slider_threads = ctk.CTkSlider(
            t_frame, from_=10, to=1000, number_of_steps=99,
            command=lambda v: self.stress_lbl_threads.configure(text=f"Threads: {int(v)}"),
            button_color=COLORS["accent"], button_hover_color=COLORS["accent_hover"]
        )
        self.stress_slider_threads.set(100)
        self.stress_slider_threads.pack(fill="x", pady=5)

        # Duration slider
        d_frame = ctk.CTkFrame(slider_row, fg_color="transparent")
        d_frame.grid(row=0, column=1, sticky="nsew", padx=5)
        self.stress_lbl_duration = ctk.CTkLabel(d_frame, text="Duration: 60s")
        self.stress_lbl_duration.pack(anchor="w")
        self.stress_slider_duration = ctk.CTkSlider(
            d_frame, from_=10, to=300, number_of_steps=29,
            command=lambda v: self.stress_lbl_duration.configure(text=f"Duration: {int(v)}s"),
            button_color=COLORS["accent"], button_hover_color=COLORS["accent_hover"]
        )
        self.stress_slider_duration.set(60)
        self.stress_slider_duration.pack(fill="x", pady=5)

        # RPS Limit slider
        r_frame = ctk.CTkFrame(slider_row, fg_color="transparent")
        r_frame.grid(row=0, column=2, sticky="nsew", padx=5)
        self.stress_lbl_rps = ctk.CTkLabel(r_frame, text="RPS Limit: Unlimited")
        self.stress_lbl_rps.pack(anchor="w")
        self.stress_slider_rps = ctk.CTkSlider(
            r_frame, from_=0, to=10000, number_of_steps=100,
            command=self.update_stress_rps_label,
            button_color=COLORS["accent"], button_hover_color=COLORS["accent_hover"]
        )
        self.stress_slider_rps.set(0)
        self.stress_slider_rps.pack(fill="x", pady=5)

        # Button Row
        btn_row = ctk.CTkFrame(cfg_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=20)

        self.btn_stress_start = ctk.CTkButton(
            btn_row, text="🚀 START STRESS TEST", height=45, fg_color=COLORS["success"],
            font=("Roboto", 14, "bold"), command=self.toggle_stress_test
        )
        self.btn_stress_start.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.btn_stress_pause = ctk.CTkButton(
            btn_row, text="⏸ PAUSE", height=45, fg_color=COLORS["warning"],
            font=("Roboto", 12, "bold"), width=100, command=self.toggle_stress_pause
        )
        self.btn_stress_pause.pack(side="left", padx=(0, 10))

        self.btn_stress_reset = ctk.CTkButton(
            btn_row, text="RESET", height=45, fg_color=COLORS["card"],
            font=("Roboto", 12, "bold"), width=80, command=self.reset_stress_stats
        )
        self.btn_stress_reset.pack(side="right")

        # Activity Log
        log_frame = ctk.CTkFrame(parent, fg_color="transparent")
        log_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 0))
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(log_frame, text="Stress Test Log", font=("Roboto", 11), text_color=COLORS["text_dim"]).grid(
            row=0, column=0, sticky="w", pady=(0, 4))
        self.stress_log_box = ctk.CTkTextbox(log_frame, fg_color=COLORS["card"])
        self.stress_log_box.grid(row=1, column=0, sticky="nsew")

    def update_stress_rps_label(self, value):
        """Update RPS limit label."""
        v = int(value)
        if v == 0:
            self.stress_lbl_rps.configure(text="RPS Limit: Unlimited")
        else:
            self.stress_lbl_rps.configure(text=f"RPS Limit: {v}")

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
        all_active = self.proxy_grid.get_active_objects() if hasattr(self, 'proxy_grid') else []
        http_count = sum(1 for p in all_active if p.get('type', '').upper() == 'HTTP')
        self.stress_proxy_count_label.configure(text=f"HTTP Proxies: {http_count:,}")

    def toggle_stress_test(self):
        """Start or stop the stress test."""
        if self.stress_running:
            self.stress_running = False
            self.btn_stress_start.configure(text="🚀 START STRESS TEST", fg_color=COLORS["success"])
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
                icon="warning"
            ):
                return

            self.stress_running = True
            self.btn_stress_start.configure(text="⏹ STOP STRESS TEST", fg_color=COLORS["danger"])

            # Start in separate thread
            self.stress_thread = threading.Thread(target=self.run_stress_engine, daemon=True)
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
            "requests": 0, "success": 0, "failed": 0,
            "rps": 0.0, "latency": 0.0, "proxies_used": 0
        }
        for key, lbl in self.stress_stat_labels.items():
            if key in ("rps", "latency"):
                lbl.configure(text="0.0")
            else:
                lbl.configure(text="0")
        self.stress_log("Statistics reset.")

    def run_stress_engine(self):
        """Run the stress test engine."""
        from core.stress_engine import StressEngine, StressConfig, AttackType, RequestMethod

        target_url = self.stress_entry_url.get().strip()

        # Validate URL
        if not target_url:
            self.stress_log_safe("Error: Please enter a target URL")
            self.stress_running = False
            self.after(0, lambda: self.btn_stress_start.configure(
                text="🚀 START STRESS TEST", fg_color=COLORS["success"]))
            return

        # Enforce HTTP only for stress testing
        if target_url.startswith("https://"):
            self.stress_log_safe("Warning: HTTPS detected. HTTP proxies cannot tunnel HTTPS. Converting to HTTP...")
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
        attack_type = attack_type_map.get(self.stress_attack_type.get(), AttackType.HTTP_FLOOD)

        # Map method
        method_map = {
            "GET": RequestMethod.GET,
            "POST": RequestMethod.POST,
            "HEAD": RequestMethod.HEAD,
            "PUT": RequestMethod.PUT,
            "DELETE": RequestMethod.DELETE,
        }
        method = method_map.get(self.stress_method.get(), RequestMethod.GET)

        threads = Utils.safe_int(self.stress_slider_threads.get(), default=100, min_val=10, max_val=1000)
        duration = Utils.safe_int(self.stress_slider_duration.get(), default=60, min_val=10, max_val=300)
        rps_limit = Utils.safe_int(self.stress_slider_rps.get(), default=0, min_val=0, max_val=10000)

        # Get HTTP proxies only
        all_active = self.proxy_grid.get_active_objects()
        engine_proxies = []

        for p in all_active:
            if p.get('type', '').upper() == 'HTTP':
                try:
                    engine_proxies.append(ProxyConfig(
                        host=p['ip'],
                        port=int(p['port']),
                        protocol='http'
                    ))
                except (ValueError, KeyError):
                    continue

        if not engine_proxies:
            self.stress_log_safe("Error: No HTTP proxies available. Load and test proxies first.")
            self.stress_running = False
            self.after(0, lambda: self.btn_stress_start.configure(
                text="🚀 START STRESS TEST", fg_color=COLORS["success"]))
            return

        self.stress_log_safe(f"Found {len(engine_proxies)} HTTP proxies for stress testing")

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
        self.after(0, lambda: self.btn_stress_start.configure(
            text="🚀 START STRESS TEST", fg_color=COLORS["success"]))
        self.stress_log_safe("Stress test completed.")

    def on_stress_stats_update(self, stats):
        """Callback for stress engine stats updates."""
        def update_on_main():
            self.stress_stat_labels["requests"].configure(text=f"{stats.requests_sent:,}")
            self.stress_stat_labels["success"].configure(text=f"{stats.requests_success:,}")
            self.stress_stat_labels["failed"].configure(text=f"{stats.requests_failed:,}")
            self.stress_stat_labels["rps"].configure(text=f"{stats.current_rps:.1f}")
            self.stress_stat_labels["latency"].configure(text=f"{stats.avg_latency_ms:.0f}ms")
            self.stress_stat_labels["proxies"].configure(text=f"{stats.proxies_used:,}")

        self.after(0, update_on_main)

    def setup_settings_ui(self, parent):
        # Sticky header with save button (outside scrollable area)
        header = ctk.CTkFrame(parent, fg_color=COLORS["card"], height=50)
        header.pack(fill="x", pady=(0, 10))
        header.pack_propagate(False)  # Prevent shrinking

        ctk.CTkLabel(header, text="Settings", font=("Roboto", 16, "bold")).pack(side="left", padx=20, pady=10)
        self.btn_save_settings = ctk.CTkButton(header, text="SAVE SETTINGS", width=140, height=35,
                                                fg_color=COLORS["success"], hover_color="#27ae60",
                                                font=("Roboto", 12, "bold"), command=self.save_cfg)
        self.btn_save_settings.pack(side="right", padx=20, pady=8)

        # Scrollable container for all settings
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # === General Settings ===
        general_card = ctk.CTkFrame(scroll, fg_color=COLORS["card"])
        general_card.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(general_card, text="General Settings", font=("Roboto", 14, "bold")).pack(anchor="w", padx=20, pady=(15, 10))

        self.chk_headless = ctk.CTkCheckBox(general_card, text="Headless Mode (invisible browser)", fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        if self.settings.get("headless", True): self.chk_headless.select()
        self.chk_headless.pack(anchor="w", padx=20, pady=5)

        self.chk_verify_ssl = ctk.CTkCheckBox(general_card, text="Verify SSL Certificates", fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        if self.settings.get("verify_ssl", True): self.chk_verify_ssl.select()
        self.chk_verify_ssl.pack(anchor="w", padx=20, pady=(5, 15))

        # === Browser Settings (Collapsible) ===
        browser_card = ctk.CTkFrame(scroll, fg_color=COLORS["card"])
        browser_card.pack(fill="x", pady=(0, 10))

        # Header with expand/collapse button
        browser_header = ctk.CTkFrame(browser_card, fg_color="transparent")
        browser_header.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(browser_header, text="Browser Settings", font=("Roboto", 14, "bold")).pack(side="left")
        self.btn_browser_expand = ctk.CTkButton(browser_header, text="▼ Expand Paths", width=120, height=24,
                                                 fg_color=COLORS["nav"], command=self.toggle_browser_paths)
        self.btn_browser_expand.pack(side="right")

        # Browser selector
        select_frame = ctk.CTkFrame(browser_card, fg_color="transparent")
        select_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(select_frame, text="Browser:").pack(side="left")
        self.combo_browser = ctk.CTkComboBox(select_frame, values=["Auto", "Chrome", "Chromium", "Edge", "Brave", "Firefox", "Other"], width=120)
        self.combo_browser.set(self.settings.get("browser_selected", "auto").title())
        self.combo_browser.pack(side="left", padx=10)
        ctk.CTkButton(select_frame, text="Detect All", width=80, fg_color=COLORS["accent"], command=self.detect_all_browsers).pack(side="right")

        # Collapsible browser paths frame (hidden by default)
        self.browser_paths_frame = ctk.CTkFrame(browser_card, fg_color=COLORS["nav"])
        self.browser_paths_visible = False  # Track visibility

        # Chrome path
        chrome_frame = ctk.CTkFrame(self.browser_paths_frame, fg_color="transparent")
        chrome_frame.pack(fill="x", padx=10, pady=3)
        ctk.CTkLabel(chrome_frame, text="Chrome:", width=70, anchor="w").pack(side="left")
        self.entry_chrome_path = ctk.CTkEntry(chrome_frame, placeholder_text="Auto-detect")
        self.entry_chrome_path.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_chrome_path.insert(0, self.settings.get("browser_chrome_path", ""))
        ctk.CTkButton(chrome_frame, text="...", width=30, fg_color=COLORS["accent"],
                      command=lambda: self.browse_browser_path(self.entry_chrome_path)).pack(side="right")

        # Chromium path (open-source / Playwright bundled)
        chromium_frame = ctk.CTkFrame(self.browser_paths_frame, fg_color="transparent")
        chromium_frame.pack(fill="x", padx=10, pady=3)
        ctk.CTkLabel(chromium_frame, text="Chromium:", width=70, anchor="w").pack(side="left")
        self.entry_chromium_path = ctk.CTkEntry(chromium_frame, placeholder_text="Auto-detect")
        self.entry_chromium_path.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_chromium_path.insert(0, self.settings.get("browser_chromium_path", ""))
        ctk.CTkButton(chromium_frame, text="...", width=30, fg_color=COLORS["accent"],
                      command=lambda: self.browse_browser_path(self.entry_chromium_path)).pack(side="right")

        # Edge path
        edge_frame = ctk.CTkFrame(self.browser_paths_frame, fg_color="transparent")
        edge_frame.pack(fill="x", padx=10, pady=3)
        ctk.CTkLabel(edge_frame, text="Edge:", width=70, anchor="w").pack(side="left")
        self.entry_edge_path = ctk.CTkEntry(edge_frame, placeholder_text="Auto-detect")
        self.entry_edge_path.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_edge_path.insert(0, self.settings.get("browser_edge_path", ""))
        ctk.CTkButton(edge_frame, text="...", width=30, fg_color=COLORS["accent"],
                      command=lambda: self.browse_browser_path(self.entry_edge_path)).pack(side="right")

        # Brave path
        brave_frame = ctk.CTkFrame(self.browser_paths_frame, fg_color="transparent")
        brave_frame.pack(fill="x", padx=10, pady=3)
        ctk.CTkLabel(brave_frame, text="Brave:", width=70, anchor="w").pack(side="left")
        self.entry_brave_path = ctk.CTkEntry(brave_frame, placeholder_text="Auto-detect")
        self.entry_brave_path.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_brave_path.insert(0, self.settings.get("browser_brave_path", ""))
        ctk.CTkButton(brave_frame, text="...", width=30, fg_color=COLORS["accent"],
                      command=lambda: self.browse_browser_path(self.entry_brave_path)).pack(side="right")

        # Firefox path
        firefox_frame = ctk.CTkFrame(self.browser_paths_frame, fg_color="transparent")
        firefox_frame.pack(fill="x", padx=10, pady=3)
        ctk.CTkLabel(firefox_frame, text="Firefox:", width=70, anchor="w").pack(side="left")
        self.entry_firefox_path = ctk.CTkEntry(firefox_frame, placeholder_text="Auto-detect")
        self.entry_firefox_path.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_firefox_path.insert(0, self.settings.get("browser_firefox_path", ""))
        ctk.CTkButton(firefox_frame, text="...", width=30, fg_color=COLORS["accent"],
                      command=lambda: self.browse_browser_path(self.entry_firefox_path)).pack(side="right")

        # Other browser path
        other_frame = ctk.CTkFrame(self.browser_paths_frame, fg_color="transparent")
        other_frame.pack(fill="x", padx=10, pady=(3, 10))
        ctk.CTkLabel(other_frame, text="Other:", width=70, anchor="w").pack(side="left")
        self.entry_other_path = ctk.CTkEntry(other_frame, placeholder_text="Custom browser path")
        self.entry_other_path.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_other_path.insert(0, self.settings.get("browser_other_path", ""))
        ctk.CTkButton(other_frame, text="...", width=30, fg_color=COLORS["accent"],
                      command=lambda: self.browse_browser_path(self.entry_other_path)).pack(side="right")

        # Browser contexts slider
        ctx_frame = ctk.CTkFrame(browser_card, fg_color="transparent")
        ctx_frame.pack(fill="x", padx=20, pady=5)
        self.lbl_contexts = ctk.CTkLabel(ctx_frame, text=f"Browser Contexts: {self.settings.get('browser_contexts', 5)}")
        self.lbl_contexts.pack(anchor="w")
        self.slider_contexts = ctk.CTkSlider(ctx_frame, from_=1, to=10, number_of_steps=9,
                                              command=lambda v: self.lbl_contexts.configure(text=f"Browser Contexts: {int(v)}"),
                                              button_color=COLORS["accent"], button_hover_color=COLORS["accent_hover"])
        self.slider_contexts.set(self.settings.get("browser_contexts", 5))
        self.slider_contexts.pack(fill="x", pady=2)

        self.chk_stealth = ctk.CTkCheckBox(browser_card, text="Enable Stealth Mode (anti-detection)", fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        if self.settings.get("browser_stealth", True): self.chk_stealth.select()
        self.chk_stealth.pack(anchor="w", padx=20, pady=(5, 15))

        # === Captcha Solving (Multi-Provider) ===
        captcha_card = ctk.CTkFrame(scroll, fg_color=COLORS["card"])
        captcha_card.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(captcha_card, text="Captcha Solving", font=("Roboto", 14, "bold")).pack(anchor="w", padx=20, pady=(15, 10))

        # Primary provider selector
        provider_frame = ctk.CTkFrame(captcha_card, fg_color="transparent")
        provider_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(provider_frame, text="Primary:").pack(side="left")
        self.combo_captcha_primary = ctk.CTkComboBox(provider_frame, values=["Auto", "2captcha", "AntiCaptcha", "None"], width=120)
        primary = self.settings.get("captcha_primary", "auto")
        self.combo_captcha_primary.set("Auto" if primary == "auto" else ("None" if primary == "none" else primary))
        self.combo_captcha_primary.pack(side="left", padx=10)

        self.chk_captcha_fallback = ctk.CTkCheckBox(provider_frame, text="Fallback on failure", fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        if self.settings.get("captcha_fallback_enabled", True): self.chk_captcha_fallback.select()
        self.chk_captcha_fallback.pack(side="right", padx=10)

        # 2captcha API Key
        key_2cap_frame = ctk.CTkFrame(captcha_card, fg_color="transparent")
        key_2cap_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(key_2cap_frame, text="2captcha Key:", width=100, anchor="w").pack(side="left")
        self.entry_2captcha_key = ctk.CTkEntry(key_2cap_frame, placeholder_text="Enter 2captcha API key", show="*")
        self.entry_2captcha_key.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_2captcha_key.insert(0, self.settings.get("captcha_2captcha_key", ""))

        # AntiCaptcha API Key
        key_anti_frame = ctk.CTkFrame(captcha_card, fg_color="transparent")
        key_anti_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(key_anti_frame, text="AntiCaptcha Key:", width=100, anchor="w").pack(side="left")
        self.entry_anticaptcha_key = ctk.CTkEntry(key_anti_frame, placeholder_text="Enter AntiCaptcha API key", show="*")
        self.entry_anticaptcha_key.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_anticaptcha_key.insert(0, self.settings.get("captcha_anticaptcha_key", ""))

        # Check balance button and status
        balance_frame = ctk.CTkFrame(captcha_card, fg_color="transparent")
        balance_frame.pack(fill="x", padx=20, pady=(5, 15))
        ctk.CTkButton(balance_frame, text="Check Balances", width=120, fg_color=COLORS["accent"], command=self.check_captcha_balance).pack(side="left")
        self.lbl_captcha_balance = ctk.CTkLabel(balance_frame, text="", text_color=COLORS["text_dim"])
        self.lbl_captcha_balance.pack(side="left", padx=15)

        # === Protection Bypass ===
        bypass_card = ctk.CTkFrame(scroll, fg_color=COLORS["card"])
        bypass_card.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(bypass_card, text="Protection Bypass", font=("Roboto", 14, "bold")).pack(anchor="w", padx=20, pady=(15, 10))

        self.chk_cloudflare = ctk.CTkCheckBox(bypass_card, text="Cloudflare Bypass", fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        if self.settings.get("cloudflare_bypass", True): self.chk_cloudflare.select()
        self.chk_cloudflare.pack(anchor="w", padx=20, pady=5)

        self.chk_akamai = ctk.CTkCheckBox(bypass_card, text="Akamai Bypass", fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        if self.settings.get("akamai_bypass", True): self.chk_akamai.select()
        self.chk_akamai.pack(anchor="w", padx=20, pady=5)

        self.chk_auto_captcha = ctk.CTkCheckBox(bypass_card, text="Auto-solve Captchas (requires API key)", fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        if self.settings.get("auto_solve_captcha", True): self.chk_auto_captcha.select()
        self.chk_auto_captcha.pack(anchor="w", padx=20, pady=(5, 15))

        # Cloudflare wait time
        wait_frame = ctk.CTkFrame(bypass_card, fg_color="transparent")
        wait_frame.pack(fill="x", padx=20, pady=(0, 15))
        ctk.CTkLabel(wait_frame, text="Cloudflare Wait (seconds):").pack(side="left")
        self.entry_cf_wait = ctk.CTkEntry(wait_frame, width=60)
        self.entry_cf_wait.insert(0, str(self.settings.get("cloudflare_wait", 10)))
        self.entry_cf_wait.pack(side="left", padx=10)

        # === Proxy Validators ===
        validator_card = ctk.CTkFrame(scroll, fg_color=COLORS["card"])
        validator_card.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(validator_card, text="Proxy Validators", font=("Roboto", 14, "bold")).pack(anchor="w", padx=20, pady=(15, 5))
        ctk.CTkLabel(validator_card, text="Select endpoints for anonymity testing", font=("Roboto", 10),
                     text_color=COLORS["text_dim"]).pack(anchor="w", padx=20, pady=(0, 10))

        # Test depth selector
        depth_frame = ctk.CTkFrame(validator_card, fg_color="transparent")
        depth_frame.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(depth_frame, text="Test Depth:").pack(side="left")
        self.combo_test_depth = ctk.CTkComboBox(depth_frame, values=["Quick", "Normal", "Thorough"], width=100)
        current_depth = self.settings.get("validator_test_depth", "quick").title()
        self.combo_test_depth.set(current_depth)
        self.combo_test_depth.pack(side="left", padx=10)
        ctk.CTkLabel(depth_frame, text="(Quick=1, Normal=3, Thorough=All)", font=("Roboto", 10),
                     text_color=COLORS["text_dim"]).pack(side="left", padx=5)

        # Validator checkboxes
        self.validator_checkboxes = {}
        validators_enabled = self.settings.get("validators_enabled", {})

        validators_frame = ctk.CTkFrame(validator_card, fg_color=COLORS["nav"])
        validators_frame.pack(fill="x", padx=20, pady=(0, 15))

        for validator in DEFAULT_VALIDATORS:
            v_frame = ctk.CTkFrame(validators_frame, fg_color="transparent")
            v_frame.pack(fill="x", padx=10, pady=3)

            chk = ctk.CTkCheckBox(v_frame, text=validator.name, width=120,
                                   fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
            if validators_enabled.get(validator.name, validator.enabled):
                chk.select()
            chk.pack(side="left")

            ctk.CTkLabel(v_frame, text=f"({validator.validator_type.value})",
                        font=("Roboto", 10), text_color=COLORS["text_dim"]).pack(side="left", padx=5)
            ctk.CTkLabel(v_frame, text=validator.description,
                        font=("Roboto", 10), text_color=COLORS["text_dim"]).pack(side="right", padx=10)

            self.validator_checkboxes[validator.name] = chk

        # === Save Button ===
        ctk.CTkButton(scroll, text="Save Configuration", height=40, fg_color=COLORS["success"],
                      font=("Roboto", 12, "bold"), command=self.save_cfg).pack(fill="x", pady=10)

    def toggle_browser_paths(self):
        """Toggle visibility of browser paths section."""
        if self.browser_paths_visible:
            self.browser_paths_frame.pack_forget()
            self.btn_browser_expand.configure(text="▼ Expand Paths")
            self.browser_paths_visible = False
        else:
            # Insert after the select frame but before context slider
            self.browser_paths_frame.pack(fill="x", padx=20, pady=5, after=self.combo_browser.master)
            self.btn_browser_expand.configure(text="▲ Collapse")
            self.browser_paths_visible = True

    def browse_browser_path(self, entry_widget):
        """Open file dialog to select browser executable for a specific entry."""
        path = filedialog.askopenfilename(
            title="Select Browser Executable",
            filetypes=[("Executable", "*.exe"), ("All Files", "*.*")]
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
            messagebox.showwarning("Browser Detection", "No browsers found.\n\nPlease install Chrome, Chromium, Edge, Brave, or Firefox,\nor run: playwright install chromium")
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
        messagebox.showinfo("Browser Detection", f"Found {len(browsers)} browser(s):\n\n" + "\n".join(
            [f"• {b.name}: {b.path}" for b in browsers]
        ))

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
                from core.models import CaptchaConfig, CaptchaProvider
                from core.captcha_manager import CaptchaManager

                config = CaptchaConfig(
                    twocaptcha_key=key_2cap,
                    anticaptcha_key=key_anti,
                    primary_provider=CaptchaProvider.AUTO
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

                self.after(0, lambda: self.lbl_captcha_balance.configure(
                    text=balance_text,
                    text_color=COLORS["success"] if has_positive else COLORS["warning"]
                ))
            except ImportError:
                self.after(0, lambda: self.lbl_captcha_balance.configure(
                    text="aiohttp not installed",
                    text_color=COLORS["danger"]
                ))
            except Exception as e:
                self.after(0, lambda: self.lbl_captcha_balance.configure(text=f"Balance: Error - {e}"))

        threading.Thread(target=_check, daemon=True).start()

    def log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def load_proxy_file(self):
        f = filedialog.askopenfilename()
        if f:
            try:
                self.proxies = []
                self.buffer = Queue()  # Reset with fresh queue
                self.proxy_grid.clear()

                with open(f, 'r') as file:
                    for l in file:
                        l = l.strip()
                        if not l: continue
                        # Normalize: Add http:// if no protocol specified (standardizes for dedup)
                        if "://" not in l:
                            l = "http://" + l
                        self.proxies.append(l)

                self.proxies = Utils.deduplicate_proxies(self.proxies)

                self.update_proxy_stats()
                self.log(f"Cleared previous data. Loaded {len(self.proxies)} unique proxies.")
            except (IOError, OSError, UnicodeDecodeError) as e:
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

    def export_active(self):
        active_objs = self.proxy_grid.get_active_objects()

        if not active_objs:
            return self.log("No active proxies to export.")

        if not os.path.exists("resources/proxies"):
            os.makedirs("resources/proxies")

        socks_list = []
        http_list = []

        for p in active_objs:
            p_str = f"{p['type'].lower()}://{p['ip']}:{p['port']}"
            if "SOCKS" in p['type']:
                socks_list.append(p_str)
            else:
                http_list.append(p_str)

        try:
            if socks_list:
                with open("resources/proxies/socks.txt", "w") as f: f.write("\n".join(socks_list))
            if http_list:
                with open("resources/proxies/http.txt", "w") as f: f.write("\n".join(http_list))

            self.log(f"Auto-Exported: {len(socks_list)} SOCKS, {len(http_list)} HTTP.")
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
                    "anonymity": p.get("anonymity", "Unknown")
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

        self.destroy()

    def run_scraper(self):
        scrape_threads = Utils.safe_int(self.entry_scrape_threads.get(), default=20, min_val=1, max_val=100)

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
        if self.chk_http.get(): protos.append("http")
        if self.chk_socks4.get(): protos.append("socks4")
        if self.chk_socks5.get(): protos.append("socks5")
        
        # Resolve sources file path relative to app directory
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sources_file = os.path.join(app_dir, self.settings["sources"])

        # Ensure sources file exists with defaults
        if not os.path.exists(sources_file):
            os.makedirs(os.path.dirname(sources_file), exist_ok=True)
            with open(sources_file, "w") as f:
                f.write("https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt\n")
                f.write("https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt\n")
                f.write("https://api.proxyscrape.com/v2/?request=getproxies&protocol=http,socks4,socks5&timeout=10000&country=all\n")

        def _job():
            self.log_safe(f"Scraping started (Async) using proxy: {system_proxy if system_proxy else 'Direct'}...")
            try:
                with open(sources_file, "r") as f:
                    urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
                
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
                        pass # Logic inside ThreadedProxyManager returns bytes per call? Yes.
                
                # Improved bandwidth tracking with closure state
                scrape_bytes_buffer = 0
                scrape_total_bytes = 0

                def on_progress_wrapper(b):
                    nonlocal scrape_bytes_buffer, scrape_total_bytes, last_time
                    scrape_bytes_buffer += b
                    scrape_total_bytes += b
                    now = time.time()
                    if now - last_time >= 1.0:
                        mbps = (scrape_bytes_buffer * 8) / 1024 / 1024 / (now - last_time)
                        total_mb = scrape_total_bytes / (1024 * 1024)
                        self.after(0, lambda m=mbps, t=total_mb: self.lbl_bandwidth.configure(
                            text=f"Scrape: {m:.2f} Mbps ({t:.1f} MB)"))
                        last_time = now
                        scrape_bytes_buffer = 0

                # Run threaded scraper
                results = manager.scrape(urls, protos, max_threads=scrape_threads, scraper_proxy=system_proxy, on_progress=on_progress_wrapper)
                
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
                self.after(0, lambda: messagebox.showinfo(
                    "Scrape Complete",
                    f"Found {len(results)} new proxies.\nTotal proxies loaded: {total}"
                ))
            except Exception as e:
                self.log_safe(f"Scrape Error: {e}")

        threading.Thread(target=_job, daemon=True).start()

    def update_proxy_stats(self):
        total = len(self.proxies)
        self.lbl_loaded.configure(text=f"Total: {total}")

        # Single-pass stats collection (more efficient than separate calls)
        counts, anon_counts = self.proxy_grid.get_all_stats()
        self.lbl_proto_counts.configure(
            text=f"HTTP: {counts['HTTP']} | HTTPS: {counts['HTTPS']} | SOCKS4: {counts['SOCKS4']} | SOCKS5: {counts['SOCKS5']}")
        self.lbl_anon_counts.configure(
            text=f"Elite: {anon_counts['Elite']} | Anonymous: {anon_counts['Anonymous']} | Transparent: {anon_counts['Transparent']} | Unknown: {anon_counts['Unknown']}")

        # Update stress test HTTP proxy count
        if hasattr(self, 'stress_proxy_count_label'):
            self.stress_proxy_count_label.configure(text=f"HTTP Proxies: {counts['HTTP']:,}")

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

        self.btn_test_proxy.configure(text="...", state="disabled", fg_color=COLORS["warning"])

        def _test():
            self.log(f"Testing system proxy: {system_proxy}...")
            try:
                proxies = {"http": system_proxy, "https": system_proxy}
                r = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=10)
                if r.status_code == 200:
                    self.log(f"System Proxy OK! Exit IP: {r.json().get('ip')}")
                    self.after(0, lambda: self.btn_test_proxy.configure(text="OK", fg_color=COLORS["success"]))
                else:
                    self.log(f"System Proxy Failed: HTTP {r.status_code}")
                    self.after(0, lambda: self.btn_test_proxy.configure(text="FAIL", fg_color=COLORS["danger"]))
            except Exception as e:
                self.log(f"System Proxy Error: {e}")
                self.after(0, lambda: self.btn_test_proxy.configure(text="ERR", fg_color=COLORS["danger"]))

            # Reset button after 2 seconds
            def reset():
                self.btn_test_proxy.configure(text="TEST", state="normal", fg_color=COLORS["accent"])
            self.after(2000, reset)

        threading.Thread(target=_test, daemon=True).start()

    def toggle_pause_test(self):
        if not self.testing: return
        self.testing_paused = not self.testing_paused
        if self.testing_paused:
            self.btn_pause.configure(text="▶ RESUME", fg_color=COLORS["success"])
            self.log("Testing PAUSED - You can change settings now. Click RESUME to continue.")
        else:
            self.btn_pause.configure(text="⏸ PAUSE", fg_color=COLORS["warning"])
            self.log("Testing RESUMED.")

    def toggle_test(self):
        if self.testing:
            self.testing = False
            self.testing_paused = False
            self.btn_test.configure(text="TEST ALL", fg_color=COLORS["success"])
            self.btn_pause.configure(state="disabled", text="⏸ PAUSE", fg_color=COLORS["warning"])
            # Save proxies when user stops testing
            self.save_checked_proxies()
            self.log("Saved checked proxies.")
        else:
            if not self.proxies: return self.log("Load proxies first.")
            self.testing = True
            self.testing_paused = False
            self.btn_test.configure(text="STOP", fg_color=COLORS["danger"])
            self.btn_pause.configure(state="normal", text="⏸ PAUSE", fg_color=COLORS["warning"])

            self.proxy_grid.clear()
            self.checked_proxies = []  # Clear for new test run
            threading.Thread(target=self.tester_thread, daemon=True).start()

    def tester_thread(self):
        self.progress_bar.pack(fill="x", pady=(0, 5))
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
                    self.log_safe("Invalid test URL. Must start with http:// or https://")
                    self.testing = False
                    self.after(0, lambda: self.progress_bar.pack_forget())
                    self.after(0, lambda: self.btn_test.configure(text="TEST ALL", fg_color=COLORS["success"]))
                    return
                self.log_safe(f"Using manual target: {url}")
            else:
                # Use first enabled validator as test URL
                if not active_validators:
                    self.log_safe("No validators enabled! Enable at least one validator in Settings.")
                    self.testing = False
                    self.after(0, lambda: self.progress_bar.pack_forget())
                    self.after(0, lambda: self.btn_test.configure(text="TEST ALL", fg_color=COLORS["success"]))
                    return
                url = active_validators[0].url
                self.log_safe(f"Using validators (primary: {active_validators[0].name})")

            timeout_ms = Utils.safe_int(self.entry_timeout.get(), default=3000, min_val=100, max_val=30000)
            check_threads = Utils.safe_int(self.entry_check_threads.get(), default=50, min_val=1, max_val=10000)
            hide_dead = self.chk_hide_dead.get()

            # Check if system proxy should be used for checking
            use_proxy_for_check = self.chk_proxy_for_check.get()
            system_proxy = self.entry_system_proxy.get().strip() if use_proxy_for_check else None
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
            if self.chk_http.get(): allowed_protos.append("http")
            if self.chk_socks4.get(): allowed_protos.append("socks4")
            if self.chk_socks5.get(): allowed_protos.append("socks5")
            
            for p_str in self.proxies:
                try:
                    if "://" in p_str:
                        parts = p_str.split("://")
                        scheme = parts[0].lower()
                        addr = parts[1]
                        
                        # Treat https as http for validation against allowed_protos
                        check_scheme = "http" if scheme == "https" else scheme
                        
                        if check_scheme not in allowed_protos: continue
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
                                check_configs.append(ProxyConfig(host=host, port=port, protocol=proto))
                        else:
                            # Map https -> http for config
                            protocol = "http" if scheme == "https" else scheme
                            check_configs.append(ProxyConfig(host=host, port=port, protocol=protocol))
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
            if not self.testing: return # Stop signal

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
                    "anonymity": res.anonymity
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
                    "anonymity": res.anonymity
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
                        self.after(0, lambda m=mbps, t=total_mb: self.lbl_bandwidth.configure(
                            text=f"Traffic: {m:.2f} Mbps ({t:.1f} MB)"))
                        last_bandwidth_time[0] = now
                        last_bytes[0] = total_bytes[0]

                    # Single progress update
                    progress = idx / total
                    self.after(0, lambda p=progress: self.progress_bar.set(p))
                    last_ui_update = now

        test_depth = self.settings.get("validator_test_depth", "quick")

        # Run threaded check with validators
        manager.check_proxies(
            check_configs, url, timeout_ms, self.real_ip, on_progress, concurrency=check_threads,
            pause_checker=lambda: self.testing_paused,
            validators=active_validators if active_validators else None,
            test_depth=test_depth
        )

        self.testing = False
        self.after(0, lambda: self.progress_bar.pack_forget())
        self.after(0, lambda: self.btn_test.configure(text="TEST ALL", fg_color=COLORS["success"]))
        self.after(0, lambda: self.btn_pause.configure(state="disabled", text="⏸ PAUSE", fg_color=COLORS["warning"]))

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
            self.engine_thread = threading.Thread(target=self.run_async_engine, daemon=True)
            self.engine_thread.start()

    def run_async_engine(self):
        url = self.entry_url.get().strip()

        # Validate URL
        if not Utils.validate_url(url):
            self.log_safe("Invalid URL. Must start with http:// or https://")
            self.running = False
            self.after(0, lambda: self.btn_attack.configure(text="START CAMPAIGN", fg_color=COLORS["success"]))
            return

        threads = Utils.safe_int(self.slider_threads.get(), default=1, min_val=1, max_val=500)
        v_min = Utils.safe_int(self.slider_view_min.get(), default=5, min_val=1, max_val=300)
        v_max = Utils.safe_int(self.slider_view_max.get(), default=10, min_val=1, max_val=300)
        if v_min > v_max:
            v_min, v_max = v_max, v_min

        self.log(f"Starting Async Engine: {threads} threads on {url}")

        # Prepare Proxies
        all_active = self.proxy_grid.get_active_objects()
        allowed = []
        if self.chk_http.get(): allowed.append("HTTP")
        if self.chk_http.get(): allowed.append("HTTPS")
        if self.chk_socks4.get(): allowed.append("SOCKS4")
        if self.chk_socks5.get(): allowed.append("SOCKS5")

        engine_proxies = []
        for p in all_active:
             if any(a in p['type'] for a in allowed):
                 # Convert grid dict to ProxyConfig
                 # Grid item: {'ip': '1.2.3.4', 'port': '80', 'type': 'HTTP', ...}
                 try:
                     proto = p['type'].lower()
                     if "socks4" in proto: protocol = "socks4"
                     elif "socks5" in proto: protocol = "socks5"
                     else: protocol = "http"
                     
                     engine_proxies.append(ProxyConfig(
                         host=p['ip'],
                         port=int(p['port']),
                         protocol=protocol
                     ))
                 except (ValueError, KeyError, TypeError):
                     continue  # Skip malformed proxy entries

        if not engine_proxies and all_active:
            self.log_safe(f"Warning: Proxies active but filtered by protocol.")
        elif not engine_proxies:
            self.log_safe("No active proxies found. Running direct.")

        self.active_proxy_count = len(engine_proxies)

        # Determine engine mode
        engine_mode = self.settings.get("engine_mode", "curl")

        # Get browser selection and map to enum
        browser_selected = self.settings.get("browser_selected", "auto").lower()
        browser_selection_map = {
            "auto": BrowserSelection.AUTO,
            "chrome": BrowserSelection.CHROME,
            "chromium": BrowserSelection.CHROMIUM,
            "edge": BrowserSelection.EDGE,
            "brave": BrowserSelection.BRAVE,
            "firefox": BrowserSelection.FIREFOX,
            "other": BrowserSelection.OTHER,
        }
        selected_browser = browser_selection_map.get(browser_selected, BrowserSelection.AUTO)

        # Get captcha primary provider
        captcha_primary = self.settings.get("captcha_primary", "auto").lower()
        captcha_provider_map = {
            "auto": CaptchaProvider.AUTO,
            "2captcha": CaptchaProvider.TWOCAPTCHA,
            "anticaptcha": CaptchaProvider.ANTICAPTCHA,
            "none": CaptchaProvider.NONE,
        }
        primary_provider = captcha_provider_map.get(captcha_primary, CaptchaProvider.AUTO)

        # Build config with all settings
        config = TrafficConfig(
            target_url=url,
            max_threads=threads,
            total_visits=0,  # Infinite
            min_duration=v_min,
            max_duration=v_max,
            headless=bool(self.settings.get("headless", True)),
            verify_ssl=bool(self.settings.get("verify_ssl", True)),
            engine_mode=EngineMode.BROWSER if engine_mode == "browser" else EngineMode.CURL,
            browser=BrowserConfig(
                selected_browser=selected_browser,
                chrome_path=self.settings.get("browser_chrome_path", ""),
                chromium_path=self.settings.get("browser_chromium_path", ""),
                edge_path=self.settings.get("browser_edge_path", ""),
                brave_path=self.settings.get("browser_brave_path", ""),
                firefox_path=self.settings.get("browser_firefox_path", ""),
                other_path=self.settings.get("browser_other_path", ""),
                headless=bool(self.settings.get("browser_headless", True)),
                max_contexts=self.settings.get("browser_contexts", 5),
                locale=self.settings.get("browser_locale", "en-US"),
                timezone=self.settings.get("browser_timezone", "America/New_York"),
                stealth_enabled=bool(self.settings.get("browser_stealth", True)),
            ),
            captcha=CaptchaConfig(
                twocaptcha_key=self.settings.get("captcha_2captcha_key", ""),
                anticaptcha_key=self.settings.get("captcha_anticaptcha_key", ""),
                primary_provider=primary_provider,
                fallback_enabled=bool(self.settings.get("captcha_fallback_enabled", True)),
                timeout_seconds=self.settings.get("captcha_timeout", 120),
            ),
            protection=ProtectionBypassConfig(
                cloudflare_enabled=bool(self.settings.get("cloudflare_bypass", True)),
                cloudflare_wait_seconds=self.settings.get("cloudflare_wait", 10),
                akamai_enabled=bool(self.settings.get("akamai_bypass", True)),
                auto_solve_captcha=bool(self.settings.get("auto_solve_captcha", True)),
            ),
        )

        # Initialize appropriate engine based on mode
        if engine_mode == "browser":
            try:
                from core.browser_engine import PlaywrightTrafficEngine
                self.engine = PlaywrightTrafficEngine(config, engine_proxies, on_update=self.on_engine_update)
                self.log_safe("Starting Browser Engine (stealth mode)...")
            except ImportError as e:
                self.log_safe(f"Browser engine not available: {e}")
                self.log_safe("Falling back to curl engine. Install: pip install playwright && playwright install chromium")
                self.engine = AsyncTrafficEngine(config, engine_proxies, on_update=self.on_engine_update)
        else:
            self.engine = AsyncTrafficEngine(config, engine_proxies, on_update=self.on_engine_update)
            self.log_safe("Starting Fast Engine (curl)...")

        # Run Async Loop
        asyncio.run(self.engine.run())

        self.running = False
        self.after(0, lambda: self.btn_attack.configure(text="START CAMPAIGN", fg_color=COLORS["success"]))
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
            self.lbl_browser_contexts.configure(text=f"Contexts: {active_contexts}/{contexts_total}")

            # Captcha stats card (solved / failed / pending)
            self.lbl_captcha_stats.configure(text=f"{captcha_solved} / {captcha_failed} / {captcha_pending}")

            # Update individual balance labels
            if balance_2captcha >= 0:
                self.lbl_balance_2captcha.configure(text=f"2Cap: ${balance_2captcha:.2f}")
            if balance_anticaptcha >= 0:
                self.lbl_balance_anticaptcha.configure(text=f"Anti: ${balance_anticaptcha:.2f}")

            # Protection stats card (detected / bypassed)
            total_detected = cf_detected + ak_detected
            total_bypassed = cf_bypassed + ak_bypassed
            self.lbl_protection_stats.configure(text=f"{total_detected} / {total_bypassed}")
            if last_event:
                # Truncate long event messages
                display_event = last_event[:30] + "..." if len(last_event) > 30 else last_event
                self.lbl_protection_event.configure(text=display_event)

        self.after(0, update_on_main_thread)

    def log_safe(self, msg):
        self.after(0, lambda: self.log(msg))

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
            self.settings["threads"] = Utils.safe_int(self.slider_threads.get(), default=5, min_val=1, max_val=500)
            self.settings["viewtime_min"] = Utils.safe_int(self.slider_view_min.get(), default=5, min_val=1, max_val=300)
            self.settings["viewtime_max"] = Utils.safe_int(self.slider_view_max.get(), default=10, min_val=1, max_val=300)
            self.settings["proxy_test_url"] = test_url
            self.settings["proxy_timeout"] = Utils.safe_int(self.entry_timeout.get(), default=3000, min_val=100, max_val=30000)
            self.settings["proxy_check_threads"] = Utils.safe_int(self.entry_check_threads.get(), default=50, min_val=1, max_val=10000)
            self.settings["proxy_scrape_threads"] = Utils.safe_int(self.entry_scrape_threads.get(), default=20, min_val=1, max_val=100)
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

            # Engine mode (from dashboard selector)
            mode_value = self.mode_selector.get()
            self.settings["engine_mode"] = "browser" if "Browser" in mode_value else "curl"

            # Browser settings - individual paths
            self.settings["browser_selected"] = self.combo_browser.get().lower()
            self.settings["browser_chrome_path"] = self.entry_chrome_path.get().strip()
            self.settings["browser_chromium_path"] = self.entry_chromium_path.get().strip()
            self.settings["browser_edge_path"] = self.entry_edge_path.get().strip()
            self.settings["browser_brave_path"] = self.entry_brave_path.get().strip()
            self.settings["browser_firefox_path"] = self.entry_firefox_path.get().strip()
            self.settings["browser_other_path"] = self.entry_other_path.get().strip()
            self.settings["browser_contexts"] = Utils.safe_int(self.slider_contexts.get(), default=5, min_val=1, max_val=10)
            self.settings["browser_stealth"] = self.chk_stealth.get()
            self.settings["browser_headless"] = self.chk_headless.get()

            # Captcha settings - dual provider support
            captcha_primary = self.combo_captcha_primary.get().lower()
            self.settings["captcha_primary"] = "none" if captcha_primary == "none" else captcha_primary
            self.settings["captcha_2captcha_key"] = self.entry_2captcha_key.get().strip()
            self.settings["captcha_anticaptcha_key"] = self.entry_anticaptcha_key.get().strip()
            self.settings["captcha_fallback_enabled"] = self.chk_captcha_fallback.get()

            # Protection bypass settings
            self.settings["cloudflare_bypass"] = self.chk_cloudflare.get()
            self.settings["akamai_bypass"] = self.chk_akamai.get()
            self.settings["auto_solve_captcha"] = self.chk_auto_captcha.get()
            self.settings["cloudflare_wait"] = Utils.safe_int(self.entry_cf_wait.get(), default=10, min_val=1, max_val=60)

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
        if not hasattr(self, '_last_stats_update'):
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
