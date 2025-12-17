import customtkinter as ctk
from tkinter import Canvas
from .styles import COLORS
from .utils import Utils

class VirtualGrid(ctk.CTkFrame):
    def __init__(self, master, columns, **kwargs):
        super().__init__(master, **kwargs)
        self.data = []
        self.row_h = 30
        self.sort_key = None  # Track current sort column
        self.sort_reverse = False
        self._needs_draw = False  # Deferred drawing flag
        self._needs_sort = False  # Deferred sort flag
        self._last_draw_len = 0   # Track data length at last draw

        self.headers = ctk.CTkFrame(self, height=35, fg_color=COLORS["nav"], corner_radius=0)
        self.headers.pack(fill="x")

        self.col_map = columns
        for i, col in enumerate(columns):
            self.headers.columnconfigure(i, weight=1)
            btn = ctk.CTkButton(
                self.headers, text=col, font=("Roboto", 11, "bold"),
                fg_color="transparent", hover_color=COLORS["card"],
                text_color=COLORS["accent"], command=lambda c=col: self.sort_by(c)
            )
            btn.grid(row=0, column=i, sticky="ew")

        self.canvas = Canvas(self, bg=COLORS["bg"], highlightthickness=0)
        self.scr = ctk.CTkScrollbar(self, command=self.canvas.yview, width=14, fg_color=COLORS["bg"])
        self.canvas.configure(yscrollcommand=self.scr.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scr.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", self.draw)
        self.canvas.bind("<MouseWheel>",
                         lambda e: (self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"), self.draw()))

    def sort_by(self, col_name):
        key_map = {
            "Address": "ip", "Proto": "type", "Country": "country_code",
            "Status": "status", "Ping": "speed", "Anon": "anonymity"
        }
        key = key_map.get(col_name, "speed")
        # Toggle direction only if clicking same column, otherwise keep direction
        if self.sort_key == key:
            self.sort_reverse = not self.sort_reverse
        self.sort_key = key
        self._apply_sort()

    def _apply_sort(self, force_draw=True):
        """Apply current sort to data."""
        if not self.sort_key or not self.data:
            return
        try:
            self.data.sort(key=lambda x: x[self.sort_key], reverse=self.sort_reverse)
        except (KeyError, TypeError):
            self.data.sort(key=lambda x: str(x.get(self.sort_key, "")), reverse=self.sort_reverse)
        if force_draw:
            self.draw()
        else:
            self._needs_draw = True

    def add(self, item):
        """Add item without immediate draw - call flush() to render."""
        self.data.append(item)
        # Mark for deferred sort every 100 items (not 10 - reduces CPU)
        if self.sort_key and len(self.data) % 100 == 0:
            self._needs_sort = True
        self._needs_draw = True

    def flush(self):
        """
        Flush pending changes - apply deferred sort and draw.
        Call this periodically from GUI loop instead of drawing on every add.
        """
        if self._needs_sort and self.sort_key:
            self._apply_sort(force_draw=False)
            self._needs_sort = False

        if self._needs_draw:
            self.draw()
            self._needs_draw = False
            self._last_draw_len = len(self.data)

    def clear(self):
        self.data = []
        self._needs_draw = False
        self._needs_sort = False
        self._last_draw_len = 0
        self.canvas.delete("all")
        self.draw()

    def get_active_objects(self):
        return [d for d in self.data if d['status'] == "Active"]

    def get_active(self):
        return [f"{d['type'].lower()}://{d['ip']}:{d['port']}" for d in self.data if d['status'] == "Active"]

    def get_counts(self):
        counts = {"HTTP": 0, "HTTPS": 0, "SOCKS4": 0, "SOCKS5": 0}
        for d in self.data:
            t = d.get('type', 'HTTP').upper()
            if t == "HTTPS":
                counts["HTTPS"] += 1
            elif "HTTP" in t:
                counts["HTTP"] += 1
            elif "SOCKS4" in t:
                counts["SOCKS4"] += 1
            elif "SOCKS5" in t:
                counts["SOCKS5"] += 1
        return counts

    def get_anonymity_counts(self):
        """Get counts for each anonymity level."""
        counts = {"Elite": 0, "Anonymous": 0, "Transparent": 0, "Unknown": 0}
        for d in self.data:
            if d.get('status') != "Active":
                continue
            anon = d.get('anonymity', 'Unknown')
            if anon in counts:
                counts[anon] += 1
            else:
                counts["Unknown"] += 1
        return counts

    def get_all_stats(self):
        """
        Get all stats in a single pass - more efficient than calling
        get_counts() and get_anonymity_counts() separately.
        Returns (proto_counts, anon_counts)
        """
        proto = {"HTTP": 0, "HTTPS": 0, "SOCKS4": 0, "SOCKS5": 0}
        anon = {"Elite": 0, "Anonymous": 0, "Transparent": 0, "Unknown": 0}

        for d in self.data:
            # Protocol counts
            t = d.get('type', 'HTTP').upper()
            if t == "HTTPS":
                proto["HTTPS"] += 1
            elif "HTTP" in t:
                proto["HTTP"] += 1
            elif "SOCKS4" in t:
                proto["SOCKS4"] += 1
            elif "SOCKS5" in t:
                proto["SOCKS5"] += 1

            # Anonymity counts (only for active proxies)
            if d.get('status') == "Active":
                a = d.get('anonymity', 'Unknown')
                if a in anon:
                    anon[a] += 1
                else:
                    anon["Unknown"] += 1

        return proto, anon

    def draw(self, _=None):
        self.canvas.delete("all")
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        total_h = len(self.data) * self.row_h
        self.canvas.configure(scrollregion=(0, 0, w, total_h))

        y_off = self.canvas.yview()[0] * total_h
        start = int(y_off // self.row_h)
        end = start + int(h // self.row_h) + 2
        col_w = w / 6

        for i in range(start, min(end, len(self.data))):
            item = self.data[i]
            y = i * self.row_h
            bg_col = COLORS["card"] if i % 2 == 0 else COLORS["bg"]
            self.canvas.create_rectangle(0, y, w, y + self.row_h, fill=bg_col, width=0)

            # Build country display: [CC] City, Country or [CC] Country
            country_code = item.get('country_code', '??')
            country_name = item.get('country', '')
            city = item.get('city', '')

            # Use text-based display (Tkinter Canvas doesn't render emoji flags well)
            if city and country_code and country_code != "??":
                location_str = f"[{country_code}] {city}"
            elif country_name and country_name != "Unknown":
                location_str = f"[{country_code}] {country_name}"
            elif country_code and country_code != "??":
                location_str = f"[{country_code}]"
            else:
                location_str = "[??]"

            vals = [
                f"{item['ip']}:{item['port']}", item['type'],
                location_str,
                item['status'], f"{item['speed']} ms", item['anonymity']
            ]
            for c, val in enumerate(vals):
                # Color-code columns
                if c == 3:  # Status column
                    color = COLORS["success"] if val == "Active" else COLORS["danger"]
                elif c == 4:  # Ping column - color by speed
                    speed = item.get('speed', 9999)
                    if speed <= 2500:
                        color = COLORS["success"]  # Green
                    elif speed <= 5000:
                        color = "#F1C40F"          # Yellow
                    elif speed <= 7500:
                        color = COLORS["warning"]  # Orange
                    else:
                        color = COLORS["danger"]   # Red
                elif c == 5:  # Anonymity column - color by level
                    anon = item.get('anonymity', 'Unknown')
                    if anon == "Elite":
                        color = COLORS["success"]  # Green - best
                    elif anon == "Anonymous":
                        color = "#F1C40F"          # Yellow - ok
                    elif anon == "Transparent":
                        color = COLORS["danger"]   # Red - bad
                    else:
                        color = COLORS["text_dim"] # Gray - unknown
                else:
                    color = COLORS["text"]
                self.canvas.create_text((c * col_w) + 10, y + 15, text=str(val), fill=color, anchor="w",
                                        font=("Roboto", 10))
