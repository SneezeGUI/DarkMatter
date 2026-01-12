"""Master Control page - Distributed slave management interface."""

import secrets
import time
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from core.settings_keys import SettingsKeys
from ..components import DraggableSash
from ..scaling import scaled
from ..styles import COLORS

if TYPE_CHECKING:
    from ..app import ModernTrafficBot


class MasterControlPage:
    """Master Control page for managing distributed slaves.

    Handles:
    - WebSocket server start/stop
    - Connected slave list display
    - Task distribution (scrape, check, traffic)
    - Aggregated statistics monitoring
    - Activity logging
    """

    def __init__(self, app: "ModernTrafficBot"):
        """Initialize the master control page.

        Args:
            app: The main application instance for shared state access.
        """
        self.app = app
        self.master_server: Any | None = None
        self.relay_client: Any | None = None  # For relay mode

        # Connection mode
        self.connection_mode = "direct"  # "direct", "relay", "cloudflare"
        self.mode_selector: ctk.CTkSegmentedButton = None

        # Server configuration widgets
        self.entry_host: ctk.CTkEntry = None
        self.entry_port: ctk.CTkEntry = None
        self.entry_secret: ctk.CTkEntry = None
        self.entry_relay_url: ctk.CTkEntry = None  # For relay mode
        self.entry_tunnel_url: ctk.CTkEntry = None  # For cloudflare mode (display)
        self.btn_server: ctk.CTkButton = None
        self.lbl_server_status: ctk.CTkLabel = None
        self.lbl_mode_info: ctk.CTkLabel = None  # Mode description

        # Stats labels
        self.stat_labels: dict[str, ctk.CTkLabel] = {}

        # Slave list
        self.slave_frame: ctk.CTkScrollableFrame = None
        self.slave_rows: dict[str, ctk.CTkFrame] = {}

        # Task controls
        self.entry_target_url: ctk.CTkEntry = None
        self.slider_threads: ctk.CTkSlider = None
        self.lbl_threads: ctk.CTkLabel = None
        self.btn_scrape: ctk.CTkButton = None
        self.btn_check: ctk.CTkButton = None
        self.btn_traffic: ctk.CTkButton = None
        self.btn_stop_all: ctk.CTkButton = None

        # Scan controls
        self.entry_scan_targets: ctk.CTkEntry = None
        self.entry_scan_ports: ctk.CTkEntry = None
        self.btn_scan: ctk.CTkButton = None

        # Scan results display
        self.scan_results_frame: ctk.CTkScrollableFrame = None
        self.scan_result_rows: list[ctk.CTkFrame] = []
        self._no_results_label: ctk.CTkLabel = None
        self.btn_export_csv: ctk.CTkButton = None
        self.btn_export_json: ctk.CTkButton = None
        self.btn_clear_results: ctk.CTkButton = None

        # Log
        self.log_box: ctk.CTkTextbox = None

        # Internal state
        self._config_height = scaled(380)
        self._config_min = scaled(200)
        self._log_min = scaled(80)

    @property
    def settings(self) -> dict[str, Any]:
        """Access app settings."""
        return self.app.settings

    def setup(self, parent: ctk.CTkFrame) -> None:
        """Set up the master control UI.

        Args:
            parent: The parent frame to build the UI in.
        """
        parent.grid_rowconfigure(0, weight=0)  # Scrollable config
        parent.grid_rowconfigure(1, weight=0)  # Draggable sash
        parent.grid_rowconfigure(2, weight=1)  # Log expands
        parent.grid_columnconfigure(0, weight=1)

        # Scrollable container for config
        config_scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        config_scroll.grid(row=0, column=0, sticky="nsew", pady=(0, 0))
        config_scroll.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=0, minsize=self._config_height)

        # Draggable sash
        def on_sash_drag(delta):
            new_height = self._config_height + delta
            parent_height = parent.winfo_height()
            max_config = parent_height - self._log_min - scaled(10)
            new_height = max(self._config_min, min(new_height, max_config))
            if new_height != self._config_height:
                self._config_height = new_height
                parent.grid_rowconfigure(
                    0, weight=0, minsize=int(self._config_height)
                )

        sash = DraggableSash(
            parent,
            on_drag=on_sash_drag,
            min_above=self._config_min,
            min_below=self._log_min,
        )
        sash.grid(row=1, column=0, sticky="ew", pady=(0, 0))

        # Build UI sections
        self._setup_server_card(config_scroll)
        self._setup_stats_row(config_scroll)
        self._setup_slave_list(config_scroll)
        self._setup_task_controls(config_scroll)
        self._setup_scan_controls(config_scroll)
        self._setup_scan_results_panel(config_scroll)
        self._setup_activity_log(parent)

    def _setup_server_card(self, parent: ctk.CTkFrame) -> None:
        """Set up the server configuration card."""
        self._server_card = ctk.CTkFrame(parent, fg_color=COLORS["card"])
        self._server_card.pack(fill="x", pady=(0, 8))

        # Header row with mode selector
        header_row = ctk.CTkFrame(self._server_card, fg_color="transparent")
        header_row.pack(fill="x", padx=20, pady=(15, 10))

        ctk.CTkLabel(
            header_row,
            text="Connection Mode",
            font=("Roboto", 14, "bold"),
        ).pack(side="left")

        self.lbl_server_status = ctk.CTkLabel(
            header_row,
            text="Stopped",
            font=("Roboto", 11),
            text_color=COLORS["text_dim"],
        )
        self.lbl_server_status.pack(side="right")

        # Mode selector
        mode_row = ctk.CTkFrame(self._server_card, fg_color="transparent")
        mode_row.pack(fill="x", padx=20, pady=(0, 5))

        self.mode_selector = ctk.CTkSegmentedButton(
            mode_row,
            values=["Direct", "Relay", "Cloudflare"],
            command=self._on_mode_changed,
            font=("Roboto", 11),
        )
        saved_mode = self.settings.get(SettingsKeys.CONNECTION_MODE, "direct").capitalize()
        self.mode_selector.set(saved_mode if saved_mode in ["Direct", "Relay", "Cloudflare"] else "Direct")
        self.mode_selector.pack(side="left")

        # Mode description
        self.lbl_mode_info = ctk.CTkLabel(
            mode_row,
            text="Run server locally, slaves connect directly (requires port forwarding for WAN)",
            font=("Roboto", 10),
            text_color=COLORS["text_dim"],
        )
        self.lbl_mode_info.pack(side="left", padx=(15, 0))

        # Config row - Direct/Cloudflare mode (run server)
        self._direct_config_row = ctk.CTkFrame(self._server_card, fg_color="transparent")
        self._direct_config_row.pack(fill="x", padx=20, pady=(5, 10))

        # Host
        ctk.CTkLabel(self._direct_config_row, text="Host:", font=("Roboto", 11)).pack(
            side="left", padx=(0, 5)
        )
        self.entry_host = ctk.CTkEntry(
            self._direct_config_row,
            width=scaled(120),
            height=scaled(28),
            placeholder_text="0.0.0.0",
        )
        self.entry_host.insert(0, self.settings.get(SettingsKeys.MASTER_HOST, "0.0.0.0"))
        self.entry_host.pack(side="left", padx=(0, 15))

        # Port
        ctk.CTkLabel(self._direct_config_row, text="Port:", font=("Roboto", 11)).pack(
            side="left", padx=(0, 5)
        )
        self.entry_port = ctk.CTkEntry(
            self._direct_config_row,
            width=scaled(70),
            height=scaled(28),
            placeholder_text="8765",
        )
        self.entry_port.insert(0, str(self.settings.get(SettingsKeys.MASTER_PORT, 8765)))
        self.entry_port.pack(side="left", padx=(0, 15))

        # Secret key
        ctk.CTkLabel(self._direct_config_row, text="Secret:", font=("Roboto", 11)).pack(
            side="left", padx=(0, 5)
        )
        self.entry_secret = ctk.CTkEntry(
            self._direct_config_row,
            width=scaled(200),
            height=scaled(28),
            placeholder_text="32+ character secret key",
            show="*",
        )
        saved_secret = self.settings.get(SettingsKeys.MASTER_SECRET_KEY) or self.settings.get("master_secret", "")
        if saved_secret:
            self.entry_secret.insert(0, saved_secret)
        self.entry_secret.pack(side="left", padx=(0, 10))
        self.entry_secret.bind("<KeyRelease>", self._on_secret_updated)

        # Show/Hide button
        self.btn_show_secret = ctk.CTkButton(
            self._direct_config_row,
            text="Show",
            width=scaled(50),
            height=scaled(28),
            fg_color=COLORS["card"],
            command=self._toggle_secret_visibility,
        )
        self.btn_show_secret.pack(side="left", padx=(0, 5))

        # Generate button
        btn_generate = ctk.CTkButton(
            self._direct_config_row,
            text="Generate",
            width=scaled(70),
            height=scaled(28),
            fg_color=COLORS["card"],
            command=self._generate_secret,
        )
        btn_generate.pack(side="left", padx=(0, 15))

        # Start/Stop button
        self.btn_server = ctk.CTkButton(
            self._direct_config_row,
            text="START SERVER",
            width=scaled(120),
            height=scaled(28),
            fg_color=COLORS["success"],
            font=("Roboto", 11, "bold"),
            command=self.toggle_server,
        )
        self.btn_server.pack(side="right")

        # Config row - Relay mode (connect to relay server)
        self._relay_config_row = ctk.CTkFrame(self._server_card, fg_color="transparent")
        # Not packed initially - shown when relay mode selected

        # Relay URL
        ctk.CTkLabel(self._relay_config_row, text="Relay URL:", font=("Roboto", 11)).pack(
            side="left", padx=(0, 5)
        )
        self.entry_relay_url = ctk.CTkEntry(
            self._relay_config_row,
            width=scaled(250),
            height=scaled(28),
            placeholder_text="relay.example.com:8765",
        )
        relay_url = self.settings.get(SettingsKeys.RELAY_URL, "")
        if relay_url:
            self.entry_relay_url.insert(0, relay_url)
        self.entry_relay_url.pack(side="left", padx=(0, 15))

        # Secret for relay
        ctk.CTkLabel(self._relay_config_row, text="Secret:", font=("Roboto", 11)).pack(
            side="left", padx=(0, 5)
        )
        self.entry_relay_secret = ctk.CTkEntry(
            self._relay_config_row,
            width=scaled(200),
            height=scaled(28),
            placeholder_text="32+ character secret key",
            show="*",
        )
        if saved_secret:
            self.entry_relay_secret.insert(0, saved_secret)
        self.entry_relay_secret.pack(side="left", padx=(0, 10))
        self.entry_relay_secret.bind("<KeyRelease>", self._on_secret_updated)

        # Show/Hide for relay secret
        self.btn_show_relay_secret = ctk.CTkButton(
            self._relay_config_row,
            text="Show",
            width=scaled(50),
            height=scaled(28),
            fg_color=COLORS["card"],
            command=self._toggle_relay_secret_visibility,
        )
        self.btn_show_relay_secret.pack(side="left", padx=(0, 15))

        # Connect button for relay
        self.btn_relay_connect = ctk.CTkButton(
            self._relay_config_row,
            text="CONNECT",
            width=scaled(120),
            height=scaled(28),
            fg_color=COLORS["success"],
            font=("Roboto", 11, "bold"),
            command=self._toggle_relay_connection,
        )
        self.btn_relay_connect.pack(side="right")

        # Apply initial mode
        self._on_mode_changed(self.mode_selector.get())

    def _setup_stats_row(self, parent: ctk.CTkFrame) -> None:
        """Set up the aggregated stats display row."""
        stats_frame = ctk.CTkFrame(parent, fg_color="transparent")
        stats_frame.pack(fill="x", pady=(0, 8))
        stats_frame.grid_columnconfigure(
            (0, 1, 2, 3, 4, 5), weight=1, uniform="master_stats"
        )

        stat_configs = [
            ("slaves", "Slaves", COLORS["accent"]),
            ("requests", "Requests", COLORS["text"]),
            ("success", "Success", COLORS["success"]),
            ("failed", "Failed", COLORS["danger"]),
            ("proxies", "Proxies", COLORS["warning"]),
            ("cpu", "Avg CPU", COLORS["text_dim"]),
        ]
        for col, (key, title, color) in enumerate(stat_configs):
            card = ctk.CTkFrame(stats_frame, fg_color=COLORS["card"])
            card.grid(row=0, column=col, sticky="nsew", padx=2, pady=2)
            ctk.CTkLabel(
                card, text=title, font=("Roboto", 9), text_color=COLORS["text_dim"]
            ).pack(pady=(6, 1))
            lbl = ctk.CTkLabel(
                card, text="0", font=("Roboto", 16, "bold"), text_color=color
            )
            lbl.pack(pady=(0, 6))
            self.stat_labels[key] = lbl

    def _setup_slave_list(self, parent: ctk.CTkFrame) -> None:
        """Set up the connected slaves list."""
        card = ctk.CTkFrame(parent, fg_color=COLORS["card"])
        card.pack(fill="x", pady=(0, 8))

        # Header
        header_row = ctk.CTkFrame(card, fg_color="transparent")
        header_row.pack(fill="x", padx=20, pady=(10, 5))

        ctk.CTkLabel(
            header_row,
            text="Connected Slaves",
            font=("Roboto", 12, "bold"),
        ).pack(side="left")

        btn_refresh = ctk.CTkButton(
            header_row,
            text="Refresh",
            width=scaled(60),
            height=scaled(24),
            fg_color=COLORS["card"],
            font=("Roboto", 10),
            command=self._refresh_slave_list,
        )
        btn_refresh.pack(side="right")

        # Column headers
        col_header = ctk.CTkFrame(card, fg_color=COLORS["nav"])
        col_header.pack(fill="x", padx=10, pady=(5, 0))
        col_header.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)

        headers = ["Name", "IP", "Status", "CPU", "Memory", "Actions"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(
                col_header,
                text=h,
                font=("Roboto", 10, "bold"),
                text_color=COLORS["text_dim"],
            ).grid(row=0, column=i, sticky="w", padx=8, pady=4)

        # Scrollable slave list
        self.slave_frame = ctk.CTkScrollableFrame(
            card, fg_color="transparent", height=scaled(100)
        )
        self.slave_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.slave_frame.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)

        # Placeholder for no slaves
        self._no_slaves_label = ctk.CTkLabel(
            self.slave_frame,
            text="No slaves connected. Start the server and connect slaves.",
            font=("Roboto", 11),
            text_color=COLORS["text_dim"],
        )
        self._no_slaves_label.grid(row=0, column=0, columnspan=6, pady=20)

    def _setup_task_controls(self, parent: ctk.CTkFrame) -> None:
        """Set up the task distribution controls."""
        card = ctk.CTkFrame(parent, fg_color=COLORS["card"])
        card.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            card,
            text="Task Distribution",
            font=("Roboto", 12, "bold"),
        ).pack(anchor="w", padx=20, pady=(10, 8))

        # Target URL row
        url_row = ctk.CTkFrame(card, fg_color="transparent")
        url_row.pack(fill="x", padx=20, pady=(0, 8))

        ctk.CTkLabel(url_row, text="Target URL:", font=("Roboto", 11)).pack(
            side="left", padx=(0, 8)
        )
        self.entry_target_url = ctk.CTkEntry(
            url_row,
            placeholder_text="https://example.com",
            height=scaled(28),
        )
        self.entry_target_url.pack(side="left", fill="x", expand=True, padx=(0, 15))

        # Threads slider
        ctk.CTkLabel(url_row, text="Threads:", font=("Roboto", 11)).pack(
            side="left", padx=(0, 5)
        )
        self.lbl_threads = ctk.CTkLabel(url_row, text="50", font=("Roboto", 11))
        self.lbl_threads.pack(side="left", padx=(0, 8))

        self.slider_threads = ctk.CTkSlider(
            url_row,
            from_=10,
            to=500,
            number_of_steps=49,
            width=scaled(100),
            command=lambda v: self.lbl_threads.configure(text=str(int(v))),
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
        )
        self.slider_threads.set(50)
        self.slider_threads.pack(side="left")

        # Button row
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 15))

        self.btn_scrape = ctk.CTkButton(
            btn_row,
            text="Scrape Proxies",
            height=scaled(32),
            fg_color=COLORS["accent"],
            font=("Roboto", 11, "bold"),
            command=self._start_scrape_all,
        )
        self.btn_scrape.pack(side="left", padx=(0, 8))

        self.btn_check = ctk.CTkButton(
            btn_row,
            text="Check Proxies",
            height=scaled(32),
            fg_color=COLORS["warning"],
            font=("Roboto", 11, "bold"),
            command=self._start_check_all,
        )
        self.btn_check.pack(side="left", padx=(0, 8))

        self.btn_traffic = ctk.CTkButton(
            btn_row,
            text="Start Traffic",
            height=scaled(32),
            fg_color=COLORS["success"],
            font=("Roboto", 11, "bold"),
            command=self._start_traffic_all,
        )
        self.btn_traffic.pack(side="left", padx=(0, 8))

        self.btn_stop_all = ctk.CTkButton(
            btn_row,
            text="STOP ALL",
            height=scaled(32),
            fg_color=COLORS["danger"],
            font=("Roboto", 11, "bold"),
            command=self._stop_all_slaves,
        )
        self.btn_stop_all.pack(side="right")

    def _setup_scan_controls(self, parent: ctk.CTkFrame) -> None:
        """Set up the network scanner controls."""
        card = ctk.CTkFrame(parent, fg_color=COLORS["card"])
        card.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            card,
            text="Network Scanner (SSH/RDP)",
            font=("Roboto", 12, "bold"),
        ).pack(anchor="w", padx=20, pady=(10, 8))

        # Target row
        target_row = ctk.CTkFrame(card, fg_color="transparent")
        target_row.pack(fill="x", padx=20, pady=(0, 8))

        ctk.CTkLabel(target_row, text="Targets:", font=("Roboto", 11)).pack(
            side="left", padx=(0, 8)
        )
        self.entry_scan_targets = ctk.CTkEntry(
            target_row,
            placeholder_text="192.168.1.0/24, 10.0.0.1-254",
            height=scaled(28),
        )
        self.entry_scan_targets.pack(side="left", fill="x", expand=True, padx=(0, 15))

        ctk.CTkLabel(target_row, text="Ports:", font=("Roboto", 11)).pack(
            side="left", padx=(0, 8)
        )
        self.entry_scan_ports = ctk.CTkEntry(
            target_row,
            width=scaled(100),
            placeholder_text="22, 3389",
            height=scaled(28),
        )
        self.entry_scan_ports.insert(0, "22, 3389")
        self.entry_scan_ports.pack(side="left", padx=(0, 15))

        self.btn_scan = ctk.CTkButton(
            target_row,
            text="Scan Network",
            height=scaled(28),
            fg_color=COLORS["accent"],
            font=("Roboto", 11, "bold"),
            command=self._start_scan_all,
        )
        self.btn_scan.pack(side="right")

        # Info label
        ctk.CTkLabel(
            card,
            text="⚠️ AUTHORIZED TESTING ONLY - Use on networks you own or have permission to test",
            font=("Roboto", 9),
            text_color=COLORS["warning"],
        ).pack(anchor="w", padx=20, pady=(0, 10))

    def _setup_scan_results_panel(self, parent: ctk.CTkFrame) -> None:
        """Set up the scan results display panel."""
        card = ctk.CTkFrame(parent, fg_color=COLORS["card"])
        card.pack(fill="x", pady=(0, 8))

        # Header row with title and action buttons
        header_row = ctk.CTkFrame(card, fg_color="transparent")
        header_row.pack(fill="x", padx=20, pady=(10, 5))

        ctk.CTkLabel(
            header_row,
            text="Scan Results",
            font=("Roboto", 12, "bold"),
        ).pack(side="left")

        # Action buttons on the right
        self.btn_clear_results = ctk.CTkButton(
            header_row,
            text="Clear",
            width=scaled(50),
            height=scaled(24),
            fg_color=COLORS["danger"],
            font=("Roboto", 10),
            command=self._clear_scan_results,
        )
        self.btn_clear_results.pack(side="right", padx=(5, 0))

        self.btn_export_json = ctk.CTkButton(
            header_row,
            text="JSON",
            width=scaled(50),
            height=scaled(24),
            fg_color=COLORS["card"],
            font=("Roboto", 10),
            command=lambda: self._export_scan_results("json"),
        )
        self.btn_export_json.pack(side="right", padx=(5, 0))

        self.btn_export_csv = ctk.CTkButton(
            header_row,
            text="CSV",
            width=scaled(50),
            height=scaled(24),
            fg_color=COLORS["card"],
            font=("Roboto", 10),
            command=lambda: self._export_scan_results("csv"),
        )
        self.btn_export_csv.pack(side="right", padx=(5, 0))

        # Column headers
        col_header = ctk.CTkFrame(card, fg_color=COLORS["nav"])
        col_header.pack(fill="x", padx=10, pady=(5, 0))
        col_header.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)

        headers = ["IP:Port", "Service", "Version", "Banner", "Slave", "Time"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(
                col_header,
                text=h,
                font=("Roboto", 10, "bold"),
                text_color=COLORS["text_dim"],
            ).grid(row=0, column=i, sticky="w", padx=8, pady=4)

        # Scrollable results list
        self.scan_results_frame = ctk.CTkScrollableFrame(
            card, fg_color="transparent", height=scaled(120)
        )
        self.scan_results_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.scan_results_frame.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)

        # Placeholder for no results
        self._no_results_label = ctk.CTkLabel(
            self.scan_results_frame,
            text="No scan results yet. Start a network scan to discover hosts.",
            font=("Roboto", 11),
            text_color=COLORS["text_dim"],
        )
        self._no_results_label.grid(row=0, column=0, columnspan=6, pady=20)

    def _add_scan_result(self, entry: Any) -> None:
        """Add a scan result to the display (thread-safe callback)."""
        # Hide the "no results" placeholder
        if self._no_results_label.winfo_ismapped():
            self._no_results_label.grid_forget()

        row_idx = len(self.scan_result_rows)

        row = ctk.CTkFrame(self.scan_results_frame, fg_color="transparent")
        row.grid(row=row_idx, column=0, columnspan=6, sticky="ew", pady=1)
        row.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)

        # IP:Port
        port_color = COLORS["success"] if entry.service == "ssh" else COLORS["accent"]
        ctk.CTkLabel(
            row,
            text=f"{entry.ip}:{entry.port}",
            font=("Roboto", 10),
            text_color=port_color,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=8)

        # Service
        service_text = entry.service.upper()
        if entry.has_valid_credentials:
            service_text += " ✓"
        ctk.CTkLabel(
            row,
            text=service_text,
            font=("Roboto", 10),
            anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=8)

        # Version
        version_text = entry.version[:20] if entry.version else "-"
        ctk.CTkLabel(
            row,
            text=version_text,
            font=("Roboto", 10),
            anchor="w",
        ).grid(row=0, column=2, sticky="w", padx=8)

        # Banner (truncated)
        banner_text = entry.banner[:30] + "..." if len(entry.banner) > 30 else entry.banner or "-"
        ctk.CTkLabel(
            row,
            text=banner_text,
            font=("Roboto", 10),
            text_color=COLORS["text_dim"],
            anchor="w",
        ).grid(row=0, column=3, sticky="w", padx=8)

        # Slave name
        ctk.CTkLabel(
            row,
            text=entry.slave_name[:12] if len(entry.slave_name) > 12 else entry.slave_name,
            font=("Roboto", 10),
            anchor="w",
        ).grid(row=0, column=4, sticky="w", padx=8)

        # Scan time
        scan_time_text = f"{entry.scan_time:.0f}ms" if entry.scan_time else "-"
        ctk.CTkLabel(
            row,
            text=scan_time_text,
            font=("Roboto", 10),
            text_color=COLORS["text_dim"],
            anchor="w",
        ).grid(row=0, column=5, sticky="w", padx=8)

        self.scan_result_rows.append(row)

    def _clear_scan_results(self) -> None:
        """Clear all scan results from display and storage."""
        # Clear UI
        for row in self.scan_result_rows:
            row.destroy()
        self.scan_result_rows.clear()

        # Show placeholder
        self._no_results_label.grid(row=0, column=0, columnspan=6, pady=20)

        # Clear storage in master server
        if self.master_server:
            self.master_server.clear_scan_results()

        self.log("Scan results cleared")

    def _export_scan_results(self, format_type: str) -> None:
        """Export scan results to CSV or JSON file."""
        if not self.master_server:
            self.log("Server not running")
            return

        results = self.master_server.get_scan_results()
        if not results:
            self.log("No scan results to export")
            return

        import json
        from tkinter import filedialog

        if format_type == "csv":
            filepath = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv")],
                initialfile="scan_results.csv",
            )
            if filepath:
                try:
                    with open(filepath, "w", newline="", encoding="utf-8") as f:
                        # Header
                        f.write("IP,Port,Service,Version,Banner,Fingerprint,Slave,Username,ScanTime,Timestamp\n")
                        for r in results:
                            banner_escaped = r.banner.replace('"', '""').replace("\n", " ")
                            f.write(
                                f'"{r.ip}",{r.port},"{r.service}","{r.version}","{banner_escaped}",'
                                f'"{r.fingerprint}","{r.slave_name}","{r.username}",{r.scan_time},{r.timestamp}\n'
                            )
                    self.log(f"Exported {len(results)} results to {filepath}")
                except Exception as e:
                    self.log(f"Export failed: {e}")

        elif format_type == "json":
            filepath = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON files", "*.json")],
                initialfile="scan_results.json",
            )
            if filepath:
                try:
                    data = []
                    for r in results:
                        data.append({
                            "ip": r.ip,
                            "port": r.port,
                            "service": r.service,
                            "version": r.version,
                            "banner": r.banner,
                            "fingerprint": r.fingerprint,
                            "slave_id": r.slave_id,
                            "slave_name": r.slave_name,
                            "has_valid_credentials": r.has_valid_credentials,
                            "username": r.username,
                            "scan_time_ms": r.scan_time,
                            "timestamp": r.timestamp,
                        })
                    with open(filepath, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    self.log(f"Exported {len(results)} results to {filepath}")
                except Exception as e:
                    self.log(f"Export failed: {e}")

    def _setup_activity_log(self, parent: ctk.CTkFrame) -> None:
        """Set up the activity log panel."""
        log_frame = ctk.CTkFrame(parent, fg_color="transparent")
        log_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 0))
        log_frame.grid_rowconfigure(1, weight=1, minsize=self._log_min)
        log_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            log_frame,
            text="Master Activity Log",
            font=("Roboto", scaled(11)),
            text_color=COLORS["text_dim"],
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        self.log_box = ctk.CTkTextbox(log_frame, fg_color=COLORS["card"])
        self.log_box.grid(row=1, column=0, sticky="nsew")

    # ==================== Server Control ====================

    def toggle_server(self) -> None:
        """Toggle the master server on/off."""
        if self.master_server and self.master_server.is_running:
            self._stop_server()
        else:
            self._start_server()

    def _start_server(self) -> None:
        """Start the master WebSocket server."""
        # Import here to avoid circular imports
        from core.master_server import MasterServer

        host = self.entry_host.get().strip() or "0.0.0.0"
        port_str = self.entry_port.get().strip() or "8765"
        secret = self.entry_secret.get().strip()

        # Validate port
        try:
            port = int(port_str)
            if not 1 <= port <= 65535:
                raise ValueError("Port out of range")
        except ValueError:
            self.log("Invalid port number")
            return

        # Validate secret
        if len(secret) < 32:
            self.log("Secret key must be at least 32 characters")
            return

        # Create and start server
        self.master_server = MasterServer(
            host=host,
            port=port,
            secret_key=secret,
            callback_wrapper=lambda cb: self.app.after(0, cb),
            on_slave_connected=self._on_slave_connected,
            on_slave_disconnected=self._on_slave_disconnected,
            on_scan_result=self._add_scan_result,
            on_log=self.log,
        )

        if self.master_server.start():
            self.btn_server.configure(
                text="STOP SERVER", fg_color=COLORS["danger"]
            )
            self.lbl_server_status.configure(
                text=f"Running on {host}:{port}", text_color=COLORS["success"]
            )

            # Save settings
            self.app.settings[SettingsKeys.MASTER_HOST] = host
            self.app.settings[SettingsKeys.MASTER_PORT] = port
            self.app.settings[SettingsKeys.MASTER_SECRET_KEY] = secret
            self.app.save_cfg()

            # Start stats update timer
            self._start_stats_timer()
        else:
            self.log("Failed to start server")
            self.master_server = None

    def _stop_server(self) -> None:
        """Stop the master WebSocket server."""
        if self.master_server:
            self.master_server.stop()
            self.master_server = None

        self.btn_server.configure(text="START SERVER", fg_color=COLORS["success"])
        self.lbl_server_status.configure(
            text="Stopped", text_color=COLORS["text_dim"]
        )

        # Clear slave list
        self._clear_slave_list()
        self._update_stats_display()

    def _start_stats_timer(self) -> None:
        """Start periodic stats update timer."""
        if self.master_server and self.master_server.is_running:
            self._update_stats_display()
            self._refresh_slave_list()
            # Schedule next update
            self.app.after(2000, self._start_stats_timer)

    # ==================== Slave Management ====================

    def _on_slave_connected(self, slave_id: str, info: dict) -> None:
        """Handle slave connection."""
        self._refresh_slave_list()

    def _on_slave_disconnected(self, slave_id: str) -> None:
        """Handle slave disconnection."""
        self._refresh_slave_list()

    def _refresh_slave_list(self) -> None:
        """Refresh the slave list display."""
        if not self.master_server:
            return

        slaves = self.master_server.get_slaves()

        # Clear existing rows
        self._clear_slave_list()

        if not slaves:
            self._no_slaves_label.grid(row=0, column=0, columnspan=6, pady=20)
            return

        self._no_slaves_label.grid_forget()

        for i, slave in enumerate(slaves):
            row = ctk.CTkFrame(self.slave_frame, fg_color="transparent")
            row.grid(row=i, column=0, columnspan=6, sticky="ew", pady=1)
            row.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)

            # Name
            ctk.CTkLabel(
                row,
                text=slave.slave_name,
                font=("Roboto", 10),
                anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=8)

            # IP
            ctk.CTkLabel(
                row,
                text=slave.ip_address,
                font=("Roboto", 10),
                anchor="w",
            ).grid(row=0, column=1, sticky="w", padx=8)

            # Status
            status_color = {
                "idle": COLORS["text_dim"],
                "scraping": COLORS["accent"],
                "checking": COLORS["warning"],
                "traffic": COLORS["success"],
                "scanning": COLORS["accent"],
            }.get(slave.status, COLORS["text_dim"])

            ctk.CTkLabel(
                row,
                text=slave.status.capitalize(),
                font=("Roboto", 10),
                text_color=status_color,
            ).grid(row=0, column=2, sticky="w", padx=8)

            # CPU
            ctk.CTkLabel(
                row,
                text=f"{slave.cpu_percent:.1f}%",
                font=("Roboto", 10),
            ).grid(row=0, column=3, sticky="w", padx=8)

            # Memory
            ctk.CTkLabel(
                row,
                text=f"{slave.memory_percent:.1f}%",
                font=("Roboto", 10),
            ).grid(row=0, column=4, sticky="w", padx=8)

            # Actions
            action_frame = ctk.CTkFrame(row, fg_color="transparent")
            action_frame.grid(row=0, column=5, sticky="w", padx=8)

            btn_stop = ctk.CTkButton(
                action_frame,
                text="Stop",
                width=scaled(40),
                height=scaled(20),
                fg_color=COLORS["warning"],
                font=("Roboto", 9),
                command=lambda sid=slave.slave_id: self._stop_slave(sid),
            )
            btn_stop.pack(side="left", padx=(0, 4))

            btn_disconnect = ctk.CTkButton(
                action_frame,
                text="X",
                width=scaled(24),
                height=scaled(20),
                fg_color=COLORS["danger"],
                font=("Roboto", 9, "bold"),
                command=lambda sid=slave.slave_id: self._disconnect_slave(sid),
            )
            btn_disconnect.pack(side="left")

            self.slave_rows[slave.slave_id] = row

    def _clear_slave_list(self) -> None:
        """Clear the slave list display."""
        for row in self.slave_rows.values():
            row.destroy()
        self.slave_rows.clear()

    def _stop_slave(self, slave_id: str) -> None:
        """Stop operation on a specific slave."""
        if self.master_server:
            self.master_server.stop_slaves([slave_id])
            self.log(f"Sent stop command to slave {slave_id[:8]}...")

    def _disconnect_slave(self, slave_id: str) -> None:
        """Disconnect a specific slave."""
        if self.master_server:
            self.master_server.disconnect_slave(slave_id)

    # ==================== Task Distribution ====================

    def _start_scrape_all(self) -> None:
        """Start proxy scraping on all slaves."""
        if not self.master_server or not self.master_server.is_running:
            self.log("Server not running")
            return

        count = self.master_server.start_scrape_on_slaves()
        self.log(f"Started proxy scraping on {count} slaves")

    def _start_check_all(self) -> None:
        """Start proxy checking on all slaves."""
        if not self.master_server or not self.master_server.is_running:
            self.log("Server not running")
            return

        threads = int(self.slider_threads.get())
        count = self.master_server.start_check_on_slaves(threads=threads)
        self.log(f"Started proxy checking on {count} slaves ({threads} threads each)")

    def _start_traffic_all(self) -> None:
        """Start traffic generation on all slaves."""
        if not self.master_server or not self.master_server.is_running:
            self.log("Server not running")
            return

        target_url = self.entry_target_url.get().strip()
        if not target_url:
            self.log("Please enter a target URL")
            return

        if not target_url.startswith(("http://", "https://")):
            self.log("URL must start with http:// or https://")
            return

        threads = int(self.slider_threads.get())
        count = self.master_server.start_traffic_on_slaves(
            target_url=target_url,
            threads=threads,
        )
        self.log(f"Started traffic to {target_url} on {count} slaves")

    def _stop_all_slaves(self) -> None:
        """Stop all operations on all slaves."""
        if not self.master_server or not self.master_server.is_running:
            self.log("Server not running")
            return

        count = self.master_server.stop_slaves()
        self.log(f"Stopped operations on {count} slaves")

    def _start_scan_all(self) -> None:
        """Start network scanning on all slaves."""
        if not self.master_server or not self.master_server.is_running:
            self.log("Server not running")
            return

        # Parse targets
        targets_str = self.entry_scan_targets.get().strip()
        if not targets_str:
            self.log("Please enter target IP ranges (e.g., 192.168.1.0/24)")
            return

        # Split by comma and clean up
        targets = [t.strip() for t in targets_str.split(",") if t.strip()]

        # Parse ports
        ports_str = self.entry_scan_ports.get().strip()
        ports = []
        if ports_str:
            try:
                ports = [int(p.strip()) for p in ports_str.split(",") if p.strip()]
            except ValueError:
                self.log("Invalid port format. Use comma-separated numbers (e.g., 22, 3389)")
                return

        if not ports:
            ports = [22, 3389]  # Default SSH and RDP

        # Start scan
        count = self.master_server.start_scan_on_slaves(
            targets=targets,
            ports=ports,
        )
        self.log(f"Started network scan on {count} slaves: {len(targets)} targets, ports {ports}")

    # ==================== Stats Display ====================

    def _update_stats_display(self) -> None:
        """Update the aggregated stats display."""
        if not self.master_server:
            self.stat_labels["slaves"].configure(text="0")
            self.stat_labels["requests"].configure(text="0")
            self.stat_labels["success"].configure(text="0")
            self.stat_labels["failed"].configure(text="0")
            self.stat_labels["proxies"].configure(text="0")
            self.stat_labels["cpu"].configure(text="0%")
            return

        stats = self.master_server.get_aggregated_stats()

        self.stat_labels["slaves"].configure(text=str(stats.active_slaves))
        self.stat_labels["requests"].configure(text=f"{stats.total_requests:,}")
        self.stat_labels["success"].configure(text=f"{stats.total_success:,}")
        self.stat_labels["failed"].configure(text=f"{stats.total_failed:,}")
        self.stat_labels["proxies"].configure(text=f"{stats.total_proxies_alive:,}")
        self.stat_labels["cpu"].configure(text=f"{stats.avg_cpu:.1f}%")

    # ==================== Utilities ====================

    def _generate_secret(self) -> None:
        """Generate a new random secret key."""
        secret = secrets.token_hex(32)  # 64 character hex string
        self.entry_secret.delete(0, "end")
        self.entry_secret.insert(0, secret)
        self._on_secret_updated()
        self.log("Generated new secret key (click Show to view)")

    def _toggle_secret_visibility(self) -> None:
        """Toggle secret key visibility between masked and plain text."""
        current_show = self.entry_secret.cget("show")
        if current_show == "*":
            # Show the secret
            self.entry_secret.configure(show="")
            self.btn_show_secret.configure(text="Hide")
        else:
            # Hide the secret
            self.entry_secret.configure(show="*")
            self.btn_show_secret.configure(text="Show")

    def _toggle_relay_secret_visibility(self) -> None:
        """Toggle relay secret visibility."""
        current_show = self.entry_relay_secret.cget("show")
        if current_show == "*":
            self.entry_relay_secret.configure(show="")
            self.btn_show_relay_secret.configure(text="Hide")
        else:
            self.entry_relay_secret.configure(show="*")
            self.btn_show_relay_secret.configure(text="Show")

    def _on_secret_updated(self, event=None) -> None:
        """Handle secret key change and persist to settings."""
        # Determine which entry triggered the event by checking focus
        # or use the direct entry as default
        try:
            focused = self.app.focus_get()
        except (KeyError, AttributeError):
            focused = None

        if focused == self.entry_relay_secret:
            secret = self.entry_relay_secret.get().strip()
            # Sync to direct entry
            if self.entry_secret:
                self.entry_secret.delete(0, "end")
                self.entry_secret.insert(0, secret)
        else:
            # Default: read from direct entry (also handles generate button)
            secret = self.entry_secret.get().strip()
            # Sync to relay entry
            if self.entry_relay_secret:
                self.entry_relay_secret.delete(0, "end")
                self.entry_relay_secret.insert(0, secret)

        # Always persist to settings
        if secret:  # Only save non-empty secrets
            self.app.settings[SettingsKeys.MASTER_SECRET_KEY] = secret
            self.app.save_cfg()

    def _on_mode_changed(self, mode: str) -> None:
        """Handle connection mode change."""
        self.connection_mode = mode.lower()

        # Update mode description
        mode_descriptions = {
            "direct": "Run server locally, slaves connect directly (requires port forwarding for WAN)",
            "relay": "Connect to a relay server - both controller and slaves connect outbound (NAT friendly)",
            "cloudflare": "Run server locally with Cloudflare Tunnel for secure public access",
        }
        self.lbl_mode_info.configure(text=mode_descriptions.get(self.connection_mode, ""))

        # Show/hide appropriate config rows
        if self.connection_mode == "relay":
            self._direct_config_row.pack_forget()
            self._relay_config_row.pack(fill="x", padx=20, pady=(5, 10))
        else:
            self._relay_config_row.pack_forget()
            self._direct_config_row.pack(fill="x", padx=20, pady=(5, 10))

        # Save mode preference
        self.app.settings[SettingsKeys.CONNECTION_MODE] = self.connection_mode
        self.app.save_cfg()

    def _toggle_relay_connection(self) -> None:
        """Toggle connection to relay server (controller mode)."""
        if self.relay_client and getattr(self.relay_client, "connected", False):
            self._disconnect_from_relay()
        else:
            self._connect_to_relay()

    def _connect_to_relay(self) -> None:
        """Connect to relay server as a controller."""
        import asyncio
        import threading

        relay_url = self.entry_relay_url.get().strip()
        secret = self.entry_relay_secret.get().strip()

        if not relay_url:
            self.log("Please enter a relay URL")
            return

        if len(secret) < 32:
            self.log("Secret key must be at least 32 characters")
            return

        # Parse URL
        if ":" in relay_url:
            host, port_str = relay_url.rsplit(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                self.log("Invalid port in relay URL")
                return
        else:
            host = relay_url
            port = 8765

        self.log(f"Connecting to relay at {host}:{port}...")

        # Create controller client that connects to relay
        from core.relay_client import RelayControllerClient

        def on_relay_connected():
            self.lbl_server_status.configure(
                text=f"Connected to {host}:{port}", text_color=COLORS["success"]
            )

        self.relay_client = RelayControllerClient(
            relay_host=host,
            relay_port=port,
            secret_key=secret,
            controller_name="DM-Controller",
            on_agent_connected=self._on_slave_connected,
            on_agent_disconnected=self._on_slave_disconnected,
            on_log=self.log,
            callback_wrapper=lambda cb: self.app.after(0, cb),
            on_connected=on_relay_connected,
        )

        # Run client in background thread
        def run_client():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.relay_client.run())
            except Exception as e:
                self.app.after(0, lambda: self.log(f"Relay connection error: {e}"))
            finally:
                loop.close()

        self._relay_thread = threading.Thread(target=run_client, daemon=True)
        self._relay_thread.start()

        self.btn_relay_connect.configure(text="DISCONNECT", fg_color=COLORS["danger"])
        self.lbl_server_status.configure(text="Connecting...", text_color=COLORS["warning"])

        # Save settings
        self.app.settings[SettingsKeys.RELAY_URL] = relay_url
        self.app.settings[SettingsKeys.MASTER_SECRET_KEY] = secret
        self.app.save_cfg()

    def _disconnect_from_relay(self) -> None:
        """Disconnect from relay server."""
        self.log("Stopping relay connection...")

        if self.relay_client:
            self.relay_client.stop()
            self.relay_client = None

        # Update UI immediately
        self.btn_relay_connect.configure(text="CONNECT", fg_color=COLORS["success"])
        self.lbl_server_status.configure(text="Disconnected", text_color=COLORS["text_dim"])
        self.log("Disconnected from relay")

        # Clear slave list
        self._clear_slave_list()
        self._update_stats_display()

    def log(self, message: str) -> None:
        """Log a message to the activity log."""
        timestamp = time.strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{timestamp}] {message}\n")
        self.log_box.see("end")

    def cleanup(self) -> None:
        """Clean up resources when page is destroyed."""
        if self.master_server and self.master_server.is_running:
            self.master_server.stop()
