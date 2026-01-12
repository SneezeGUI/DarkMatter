"""Settings page - Global configuration options."""

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from core.validators import DEFAULT_VALIDATORS

from ..scaling import scaled
from ..styles import COLORS

if TYPE_CHECKING:
    from ..app import ModernTrafficBot


class SettingsPage:
    """Settings page for global configuration.

    Handles:
    - General settings (headless, SSL verification)
    - Browser configuration (paths, contexts, stealth)
    - Captcha provider configuration
    - Protection bypass settings
    - Validator selection
    """

    def __init__(self, app: "ModernTrafficBot"):
        """Initialize the settings page.

        Args:
            app: The main application instance for shared state access.
        """
        self.app = app

        # UI widget references
        self.chk_headless: ctk.CTkCheckBox = None
        self.chk_verify_ssl: ctk.CTkCheckBox = None
        self.chk_session_persist: ctk.CTkCheckBox = None
        self.combo_browser: ctk.CTkComboBox = None
        self.btn_browser_expand: ctk.CTkButton = None
        self.browser_paths_frame: ctk.CTkFrame = None
        self.browser_paths_visible: bool = False
        self.entry_chrome_path: ctk.CTkEntry = None
        self.entry_chromium_path: ctk.CTkEntry = None
        self.entry_edge_path: ctk.CTkEntry = None
        self.entry_brave_path: ctk.CTkEntry = None
        self.entry_firefox_path: ctk.CTkEntry = None
        self.entry_other_path: ctk.CTkEntry = None
        self.slider_contexts: ctk.CTkSlider = None
        self.lbl_contexts: ctk.CTkLabel = None
        self.chk_stealth: ctk.CTkCheckBox = None
        self.combo_captcha_primary: ctk.CTkComboBox = None
        self.chk_captcha_fallback: ctk.CTkCheckBox = None
        self.entry_2captcha_key: ctk.CTkEntry = None
        self.entry_anticaptcha_key: ctk.CTkEntry = None
        self.lbl_captcha_balance: ctk.CTkLabel = None
        self.chk_cloudflare: ctk.CTkCheckBox = None
        self.chk_akamai: ctk.CTkCheckBox = None
        self.chk_auto_captcha: ctk.CTkCheckBox = None
        self.entry_cf_wait: ctk.CTkEntry = None
        self.combo_test_depth: ctk.CTkComboBox = None
        self.validator_checkboxes: dict[str, ctk.CTkCheckBox] = {}

    @property
    def settings(self) -> dict[str, Any]:
        """Access app settings."""
        return self.app.settings

    def setup(self, parent: ctk.CTkFrame) -> None:
        """Set up the settings UI.

        Args:
            parent: The parent frame to build the UI in.
        """
        # Sticky header with save button
        self._setup_header(parent)

        # Scrollable container for all settings
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # Build settings sections
        self._setup_general_settings(scroll)
        self._setup_browser_settings(scroll)
        self._setup_captcha_settings(scroll)
        self._setup_bypass_settings(scroll)
        self._setup_validator_settings(scroll)

        # Bottom save button
        ctk.CTkButton(
            scroll,
            text="Save Configuration",
            height=scaled(40),
            fg_color=COLORS["success"],
            font=("Roboto", scaled(12), "bold"),
            command=self.app.save_cfg,
        ).pack(fill="x", pady=10)

    def _setup_header(self, parent: ctk.CTkFrame) -> None:
        """Set up the sticky header with save button."""
        header = ctk.CTkFrame(parent, fg_color=COLORS["card"], height=scaled(45))
        header.pack(fill="x", pady=(0, 10))
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="Settings", font=("Roboto", scaled(15), "bold")).pack(
            side="left", padx=scaled(15), pady=scaled(8)
        )

        ctk.CTkButton(
            header,
            text="SAVE SETTINGS",
            width=scaled(120),
            height=scaled(32),
            fg_color=COLORS["success"],
            hover_color="#27ae60",
            font=("Roboto", scaled(11), "bold"),
            command=self.app.save_cfg,
        ).pack(side="right", padx=scaled(15), pady=scaled(6))

    def _setup_general_settings(self, parent: ctk.CTkFrame) -> None:
        """Set up the general settings card."""
        card = ctk.CTkFrame(parent, fg_color=COLORS["card"])
        card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(card, text="General Settings", font=("Roboto", 14, "bold")).pack(
            anchor="w", padx=20, pady=(15, 10)
        )

        self.chk_headless = ctk.CTkCheckBox(
            card,
            text="Headless Mode (invisible browser)",
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        )
        if self.settings.get("headless", True):
            self.chk_headless.select()
        self.chk_headless.pack(anchor="w", padx=20, pady=5)

        self.chk_verify_ssl = ctk.CTkCheckBox(
            card,
            text="Verify SSL Certificates",
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        )
        if self.settings.get("verify_ssl", True):
            self.chk_verify_ssl.select()
        self.chk_verify_ssl.pack(anchor="w", padx=20, pady=5)

        self.chk_session_persist = ctk.CTkCheckBox(
            card,
            text="Persist Session Cookies (maintain cookies across runs)",
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        )
        if self.settings.get("session_persistence", False):
            self.chk_session_persist.select()
        self.chk_session_persist.pack(anchor="w", padx=20, pady=(5, 15))

    def _setup_browser_settings(self, parent: ctk.CTkFrame) -> None:
        """Set up the browser settings card."""
        card = ctk.CTkFrame(parent, fg_color=COLORS["card"])
        card.pack(fill="x", pady=(0, 10))

        # Header with expand button
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(15, 5))

        ctk.CTkLabel(
            header, text="Browser Settings", font=("Roboto", scaled(14), "bold")
        ).pack(side="left")

        self.btn_browser_expand = ctk.CTkButton(
            header,
            text="\u25bc Expand Paths",
            width=scaled(120),
            height=scaled(24),
            fg_color=COLORS["nav"],
            command=self.toggle_browser_paths,
        )
        self.btn_browser_expand.pack(side="right")

        # Browser selector
        select_frame = ctk.CTkFrame(card, fg_color="transparent")
        select_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(select_frame, text="Browser:").pack(side="left")
        self.combo_browser = ctk.CTkComboBox(
            select_frame,
            values=["Auto", "Chrome", "Chromium", "Edge", "Brave", "Firefox", "Other"],
            width=scaled(120),
        )
        self.combo_browser.set(self.settings.get("browser_selected", "auto").title())
        self.combo_browser.pack(side="left", padx=10)

        ctk.CTkButton(
            select_frame,
            text="Detect All",
            width=scaled(80),
            fg_color=COLORS["accent"],
            command=self.app.detect_all_browsers,
        ).pack(side="right")

        # Collapsible browser paths frame
        self.browser_paths_frame = ctk.CTkFrame(card, fg_color=COLORS["nav"])
        self._setup_browser_paths()

        # Browser contexts slider
        ctx_frame = ctk.CTkFrame(card, fg_color="transparent")
        ctx_frame.pack(fill="x", padx=20, pady=5)

        self.lbl_contexts = ctk.CTkLabel(
            ctx_frame,
            text=f"Browser Contexts: {self.settings.get('browser_contexts', 5)}",
        )
        self.lbl_contexts.pack(anchor="w")

        self.slider_contexts = ctk.CTkSlider(
            ctx_frame,
            from_=1,
            to=10,
            number_of_steps=9,
            command=lambda v: self.lbl_contexts.configure(
                text=f"Browser Contexts: {int(v)}"
            ),
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
        )
        self.slider_contexts.set(self.settings.get("browser_contexts", 5))
        self.slider_contexts.pack(fill="x", pady=2)

        self.chk_stealth = ctk.CTkCheckBox(
            card,
            text="Enable Stealth Mode (anti-detection)",
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        )
        if self.settings.get("browser_stealth", True):
            self.chk_stealth.select()
        self.chk_stealth.pack(anchor="w", padx=20, pady=(5, 15))

    def _setup_browser_paths(self) -> None:
        """Set up the browser path entries (initially hidden)."""
        browsers = [
            ("Chrome:", "entry_chrome_path", "browser_chrome_path"),
            ("Chromium:", "entry_chromium_path", "browser_chromium_path"),
            ("Edge:", "entry_edge_path", "browser_edge_path"),
            ("Brave:", "entry_brave_path", "browser_brave_path"),
            ("Firefox:", "entry_firefox_path", "browser_firefox_path"),
            ("Other:", "entry_other_path", "browser_other_path"),
        ]

        for label, attr_name, setting_key in browsers:
            frame = ctk.CTkFrame(self.browser_paths_frame, fg_color="transparent")
            frame.pack(fill="x", padx=10, pady=3)

            ctk.CTkLabel(frame, text=label, width=scaled(70), anchor="w").pack(
                side="left"
            )

            entry = ctk.CTkEntry(frame, placeholder_text="Auto-detect")
            entry.pack(side="left", fill="x", expand=True, padx=5)
            entry.insert(0, self.settings.get(setting_key, ""))

            setattr(self, attr_name, entry)

            ctk.CTkButton(
                frame,
                text="...",
                width=scaled(30),
                fg_color=COLORS["accent"],
                command=lambda e=entry: self.app.browse_browser_path(e),
            ).pack(side="right")

    def _setup_captcha_settings(self, parent: ctk.CTkFrame) -> None:
        """Set up the captcha settings card."""
        card = ctk.CTkFrame(parent, fg_color=COLORS["card"])
        card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            card, text="Captcha Solving", font=("Roboto", scaled(14), "bold")
        ).pack(anchor="w", padx=20, pady=(15, 10))

        # Primary provider selector
        provider_frame = ctk.CTkFrame(card, fg_color="transparent")
        provider_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(provider_frame, text="Primary:").pack(side="left")
        self.combo_captcha_primary = ctk.CTkComboBox(
            provider_frame,
            values=["Auto", "2captcha", "AntiCaptcha", "None"],
            width=scaled(120),
        )
        primary = self.settings.get("captcha_primary", "auto")
        self.combo_captcha_primary.set(
            "Auto" if primary == "auto" else ("None" if primary == "none" else primary)
        )
        self.combo_captcha_primary.pack(side="left", padx=10)

        self.chk_captcha_fallback = ctk.CTkCheckBox(
            provider_frame,
            text="Fallback on failure",
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        )
        if self.settings.get("captcha_fallback_enabled", True):
            self.chk_captcha_fallback.select()
        self.chk_captcha_fallback.pack(side="right", padx=10)

        # 2captcha key
        key_2cap_frame = ctk.CTkFrame(card, fg_color="transparent")
        key_2cap_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(
            key_2cap_frame, text="2captcha Key:", width=scaled(100), anchor="w"
        ).pack(side="left")
        self.entry_2captcha_key = ctk.CTkEntry(
            key_2cap_frame, placeholder_text="Enter 2captcha API key", show="*"
        )
        self.entry_2captcha_key.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_2captcha_key.insert(0, self.settings.get("captcha_2captcha_key", ""))

        # AntiCaptcha key
        key_anti_frame = ctk.CTkFrame(card, fg_color="transparent")
        key_anti_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(
            key_anti_frame, text="AntiCaptcha Key:", width=scaled(100), anchor="w"
        ).pack(side="left")
        self.entry_anticaptcha_key = ctk.CTkEntry(
            key_anti_frame, placeholder_text="Enter AntiCaptcha API key", show="*"
        )
        self.entry_anticaptcha_key.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_anticaptcha_key.insert(
            0, self.settings.get("captcha_anticaptcha_key", "")
        )

        # Balance check
        balance_frame = ctk.CTkFrame(card, fg_color="transparent")
        balance_frame.pack(fill="x", padx=20, pady=(5, 15))

        ctk.CTkButton(
            balance_frame,
            text="Check Balances",
            width=scaled(120),
            fg_color=COLORS["accent"],
            command=self.app.check_captcha_balance,
        ).pack(side="left")

        self.lbl_captcha_balance = ctk.CTkLabel(
            balance_frame, text="", text_color=COLORS["text_dim"]
        )
        self.lbl_captcha_balance.pack(side="left", padx=15)

    def _setup_bypass_settings(self, parent: ctk.CTkFrame) -> None:
        """Set up the protection bypass settings card."""
        card = ctk.CTkFrame(parent, fg_color=COLORS["card"])
        card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            card, text="Protection Bypass", font=("Roboto", scaled(14), "bold")
        ).pack(anchor="w", padx=20, pady=(15, 10))

        self.chk_cloudflare = ctk.CTkCheckBox(
            card,
            text="Cloudflare Bypass",
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        )
        if self.settings.get("cloudflare_bypass", True):
            self.chk_cloudflare.select()
        self.chk_cloudflare.pack(anchor="w", padx=20, pady=5)

        self.chk_akamai = ctk.CTkCheckBox(
            card,
            text="Akamai Bypass",
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        )
        if self.settings.get("akamai_bypass", True):
            self.chk_akamai.select()
        self.chk_akamai.pack(anchor="w", padx=20, pady=5)

        self.chk_auto_captcha = ctk.CTkCheckBox(
            card,
            text="Auto-solve Captchas (requires API key)",
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        )
        if self.settings.get("auto_solve_captcha", True):
            self.chk_auto_captcha.select()
        self.chk_auto_captcha.pack(anchor="w", padx=20, pady=(5, 15))

        # Cloudflare wait time
        wait_frame = ctk.CTkFrame(card, fg_color="transparent")
        wait_frame.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(wait_frame, text="Cloudflare Wait (seconds):").pack(side="left")
        self.entry_cf_wait = ctk.CTkEntry(wait_frame, width=scaled(60))
        self.entry_cf_wait.insert(0, str(self.settings.get("cloudflare_wait", 10)))
        self.entry_cf_wait.pack(side="left", padx=10)

    def _setup_validator_settings(self, parent: ctk.CTkFrame) -> None:
        """Set up the validator settings card."""
        card = ctk.CTkFrame(parent, fg_color=COLORS["card"])
        card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            card, text="Proxy Validators", font=("Roboto", scaled(14), "bold")
        ).pack(anchor="w", padx=20, pady=(15, 5))

        ctk.CTkLabel(
            card,
            text="Select endpoints for anonymity testing",
            font=("Roboto", scaled(10)),
            text_color=COLORS["text_dim"],
        ).pack(anchor="w", padx=20, pady=(0, 10))

        # Test depth selector
        depth_frame = ctk.CTkFrame(card, fg_color="transparent")
        depth_frame.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(depth_frame, text="Test Depth:").pack(side="left")
        self.combo_test_depth = ctk.CTkComboBox(
            depth_frame, values=["Quick", "Normal", "Thorough"], width=scaled(100)
        )
        current_depth = self.settings.get("validator_test_depth", "quick").title()
        self.combo_test_depth.set(current_depth)
        self.combo_test_depth.pack(side="left", padx=10)

        ctk.CTkLabel(
            depth_frame,
            text="(Quick=1, Normal=3, Thorough=All)",
            font=("Roboto", scaled(10)),
            text_color=COLORS["text_dim"],
        ).pack(side="left", padx=5)

        # Validator checkboxes
        validators_frame = ctk.CTkFrame(card, fg_color=COLORS["nav"])
        validators_frame.pack(fill="x", padx=20, pady=(0, 15))

        validators_enabled = self.settings.get("validators_enabled", {})

        for validator in DEFAULT_VALIDATORS:
            v_frame = ctk.CTkFrame(validators_frame, fg_color="transparent")
            v_frame.pack(fill="x", padx=10, pady=3)

            chk = ctk.CTkCheckBox(
                v_frame,
                text=validator.name,
                width=scaled(120),
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
            )
            if validators_enabled.get(validator.name, validator.enabled):
                chk.select()
            chk.pack(side="left")

            ctk.CTkLabel(
                v_frame,
                text=f"({validator.validator_type.value})",
                font=("Roboto", scaled(10)),
                text_color=COLORS["text_dim"],
            ).pack(side="left", padx=5)

            ctk.CTkLabel(
                v_frame,
                text=validator.description,
                font=("Roboto", scaled(10)),
                text_color=COLORS["text_dim"],
            ).pack(side="right", padx=10)

            self.validator_checkboxes[validator.name] = chk

    # Event handlers

    def toggle_browser_paths(self) -> None:
        """Toggle visibility of browser paths section."""
        if self.browser_paths_visible:
            self.browser_paths_frame.pack_forget()
            self.btn_browser_expand.configure(text="\u25bc Expand Paths")
            self.browser_paths_visible = False
        else:
            self.browser_paths_frame.pack(
                fill="x", padx=20, pady=5, after=self.combo_browser.master
            )
            self.btn_browser_expand.configure(text="\u25b2 Collapse")
            self.browser_paths_visible = True
