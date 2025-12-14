import customtkinter as ctk
import threading
import time
import os
import json
import re
import requests
import random
from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog, Canvas
from fake_useragent import UserAgent
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Configuration & Styling ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

COLORS = {
    "bg": "#1a1a1a",
    "nav": "#252526",
    "card": "#2b2b2b",
    "accent": "#3B8ED0",
    "accent_hover": "#36719f",
    "success": "#2CC985",
    "danger": "#C0392B",
    "text": "#ffffff",
    "text_dim": "#a1a1a1",
    "border": "#3f3f3f"
}


class Utils:
    @staticmethod
    def get_flag(code):
        if not code or len(code) != 2: return "🏳️"
        try:
            return chr(ord(code[0].upper()) + 127397) + chr(ord(code[1].upper()) + 127397)
        except:
            return "🏳️"

    @staticmethod
    def load_settings(filename="settings.json"):
        defaults = {
            "target_url": "https://example.com",
            "threads": 5,
            "viewtime": 5,
            "proxy_test_url": "http://httpbin.org/json",
            "proxy_timeout": 10,
            "proxy_check_threads": 50,
            "proxy_scrape_threads": 20,
            "use_http": True,
            "use_socks4": True,
            "use_socks5": True,
            "hide_dead": True,  # Default to True for performance
            "headless": True,
            "sources": "sources.txt"
        }
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    return {**defaults, **json.load(f)}
            except:
                pass
        return defaults

    @staticmethod
    def save_settings(data, filename="settings.json"):
        try:
            with open(filename, 'w') as f:
                json.dump(data, f, indent=4)
        except:
            pass


class ProxyEngine:
    @staticmethod
    def scrape(sources_file, protocols, max_threads=20):
        proxies = set()
        proto_str = ",".join([p for p, enabled in protocols.items() if enabled])
        if not proto_str: proto_str = "http,socks4,socks5"

        if not os.path.exists(sources_file):
            with open(sources_file, "w") as f:
                f.write("https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt\n")
                f.write("https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt\n")
                f.write(
                    f"https://api.proxyscrape.com/v2/?request=getproxies&protocol={proto_str}&timeout=10000&country=all\n")

        try:
            with open(sources_file, "r") as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        except:
            return []

        pattern = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b")

        def fetch(url):
            try:
                if "socks5" in url.lower() and not protocols.get("socks5"): return []
                if "socks4" in url.lower() and not protocols.get("socks4"): return []
                if "http" in url.lower() and not protocols.get("http"): return []

                r = requests.get(url, timeout=10)
                if r.status_code == 200: return pattern.findall(r.text)
            except:
                pass
            return []

        with ThreadPoolExecutor(max_workers=max_threads) as ex:
            results = ex.map(fetch, urls)

        for res in results: proxies.update(res)
        return list(proxies)

    @staticmethod
    def check(proxy, target, timeout, real_ip, allowed_protos):
        res = {
            "proxy": proxy, "status": "Dead", "speed": 9999,
            "country": "Unknown", "type": "HTTP", "anonymity": "-",
            "country_code": "??"
        }

        check_list = []
        if "://" in proxy:
            p_type = proxy.split("://")[0].lower()
            if allowed_protos.get(p_type, True):
                check_list = [p_type]
                clean_ip = proxy.split("://")[-1]
            else:
                return res
        else:
            clean_ip = proxy
            if allowed_protos.get("socks5"): check_list.append("socks5")
            if allowed_protos.get("socks4"): check_list.append("socks4")
            if allowed_protos.get("http"): check_list.append("http")

        for proto in check_list:
            p_str = f"{proto}://{clean_ip}"
            proxies_dict = {"http": p_str, "https": p_str}
            try:
                s = time.time()
                r = requests.get(target, proxies=proxies_dict, timeout=timeout, verify=False)
                res["speed"] = int((time.time() - s) * 1000)
                res["status"] = "Active"
                res["type"] = proto.upper()

                try:
                    data = r.json()
                    origin = data.get("origin", "").split(',')[0]
                    res["anonymity"] = "Transparent" if real_ip in origin else "Elite"
                except:
                    res["anonymity"] = "Active"

                try:
                    ip_part = clean_ip.split(':')[0]
                    geo = requests.get(f"http://ip-api.com/json/{ip_part}", timeout=3).json()
                    res["country_code"] = geo.get("countryCode", "??")
                    res["country"] = geo.get("country", "Unknown")
                except:
                    pass

                return res
            except:
                continue
        return res


class VirtualGrid(ctk.CTkFrame):
    def __init__(self, master, columns, **kwargs):
        super().__init__(master, **kwargs)
        self.data = []
        self.row_h = 30
        self.sort_reverse = False

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
        self.sort_reverse = not self.sort_reverse
        try:
            self.data.sort(key=lambda x: x[key], reverse=self.sort_reverse)
        except:
            self.data.sort(key=lambda x: str(x[key]), reverse=self.sort_reverse)
        self.draw()

    def add(self, item):
        self.data.append(item)
        self.draw()

    def clear(self):
        self.data = []
        self.canvas.delete("all")
        self.draw()

    def get_active_objects(self):
        return [d for d in self.data if d['status'] == "Active"]

    def get_active(self):
        return [f"{d['type'].lower()}://{d['ip']}:{d['port']}" for d in self.data if d['status'] == "Active"]

    def get_counts(self):
        counts = {"HTTP": 0, "SOCKS4": 0, "SOCKS5": 0}
        for d in self.data:
            t = d.get('type', 'HTTP').upper()
            if "HTTP" in t:
                counts["HTTP"] += 1
            elif "SOCKS4" in t:
                counts["SOCKS4"] += 1
            elif "SOCKS5" in t:
                counts["SOCKS5"] += 1
        return counts

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

            vals = [
                f"{item['ip']}:{item['port']}", item['type'],
                f"{Utils.get_flag(item['country_code'])} {item['country_code']}",
                item['status'], f"{item['speed']} ms", item['anonymity']
            ]
            for c, val in enumerate(vals):
                color = COLORS["success"] if c == 3 and val == "Active" else COLORS["text"]
                self.canvas.create_text((c * col_w) + 10, y + 15, text=str(val), fill=color, anchor="w",
                                        font=("Roboto", 10))


class ModernTrafficBot(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.settings = Utils.load_settings()
        self.title("DARKMATTER-TB")
        self.geometry("1100x750")

        self.testing = False
        self.running = False
        self.proxies = []
        self.buffer = []
        self.stats = {"req": 0, "success": 0, "fail": 0}

        try:
            self.real_ip = requests.get("https://api.ipify.org", timeout=2).text
        except:
            self.real_ip = "0.0.0.0"

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.setup_sidebar()
        self.setup_pages()
        self.select_page("run")
        self.update_gui_loop()

    def setup_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0, fg_color=COLORS["nav"])
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(4, weight=1)

        ctk.CTkLabel(self.sidebar, text="DARKMATTER", font=("Roboto", 20, "bold"), text_color=COLORS["accent"]).grid(
            row=0, column=0, padx=20, pady=(20, 10))

        self.nav_btns = {}
        for i, (key, text) in enumerate(
                [("run", "🚀 Dashboard"), ("proxy", "🛡️ Proxy Manager"), ("settings", "⚙️ Settings")]):
            btn = ctk.CTkButton(self.sidebar, text=text, fg_color="transparent", text_color=COLORS["text_dim"],
                                anchor="w", hover_color=COLORS["card"], height=40,
                                command=lambda k=key: self.select_page(k))
            btn.grid(row=i + 1, column=0, sticky="ew", padx=10, pady=5)
            self.nav_btns[key] = btn

        ctk.CTkLabel(self.sidebar, text="v3.0.6 Performance", text_color=COLORS["text_dim"], font=("Roboto", 10)).grid(
            row=5,
            column=0,
            pady=20)

    def setup_pages(self):
        self.pages = {}
        self.pages["run"] = ctk.CTkFrame(self, fg_color="transparent")
        self.setup_run_ui(self.pages["run"])
        self.pages["proxy"] = ctk.CTkFrame(self, fg_color="transparent")
        self.setup_proxy_ui(self.pages["proxy"])
        self.pages["settings"] = ctk.CTkFrame(self, fg_color="transparent")
        self.setup_settings_ui(self.pages["settings"])

    def select_page(self, key):
        for k, p in self.pages.items(): p.grid_forget()
        for k, b in self.nav_btns.items(): b.configure(fg_color="transparent", text_color=COLORS["text_dim"])
        self.pages[key].grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.nav_btns[key].configure(fg_color=COLORS["card"], text_color=COLORS["text"])

    def setup_run_ui(self, parent):
        stats_frame = ctk.CTkFrame(parent, fg_color="transparent")
        stats_frame.pack(fill="x", pady=(0, 20))

        self.lbl_stats = {}
        for key, title in [("req", "Total Requests"), ("success", "Successful Visits"), ("fail", "Failed / Timeout")]:
            card = ctk.CTkFrame(stats_frame, fg_color=COLORS["card"])
            card.pack(side="left", fill="x", expand=True, padx=5)
            ctk.CTkLabel(card, text=title, font=("Roboto", 12), text_color=COLORS["text_dim"]).pack(pady=(15, 0))
            l = ctk.CTkLabel(card, text="0", font=("Roboto", 28, "bold"), text_color=COLORS["accent"])
            l.pack(pady=(0, 15))
            self.lbl_stats[key] = l

        cfg_frame = ctk.CTkFrame(parent, fg_color=COLORS["card"])
        cfg_frame.pack(fill="x", pady=10)

        ctk.CTkLabel(cfg_frame, text="Attack Configuration", font=("Roboto", 14, "bold")).pack(anchor="w", padx=20,
                                                                                               pady=15)

        self.entry_url = ctk.CTkEntry(cfg_frame, placeholder_text="https://target.com", height=35)
        self.entry_url.pack(fill="x", padx=20, pady=(0, 15))
        self.entry_url.insert(0, self.settings["target_url"])

        slider_row = ctk.CTkFrame(cfg_frame, fg_color="transparent")
        slider_row.pack(fill="x", padx=10, pady=10)

        t_frame = ctk.CTkFrame(slider_row, fg_color="transparent")
        t_frame.pack(side="left", fill="x", expand=True)

        self.lbl_threads = ctk.CTkLabel(t_frame, text=f"Concurrent Threads: {self.settings.get('threads', 5)}")
        self.lbl_threads.pack(anchor="w")

        self.slider_threads = ctk.CTkSlider(t_frame, from_=1, to=100, number_of_steps=99,
                                            command=self.update_thread_lbl)
        self.slider_threads.set(self.settings.get("threads", 5))
        self.slider_threads.pack(fill="x", pady=5)

        v_frame = ctk.CTkFrame(slider_row, fg_color="transparent")
        v_frame.pack(side="left", fill="x", expand=True, padx=20)

        self.lbl_viewtime = ctk.CTkLabel(v_frame, text=f"View Duration: {self.settings.get('viewtime', 5)}s")
        self.lbl_viewtime.pack(anchor="w")

        self.slider_viewtime = ctk.CTkSlider(v_frame, from_=1, to=60, number_of_steps=59, command=self.update_view_lbl)
        self.slider_viewtime.set(self.settings.get("viewtime", 5))
        self.slider_viewtime.pack(fill="x", pady=5)

        self.btn_attack = ctk.CTkButton(cfg_frame, text="START CAMPAIGN", height=45, fg_color=COLORS["success"],
                                        font=("Roboto", 14, "bold"), command=self.toggle_attack)
        self.btn_attack.pack(fill="x", padx=20, pady=20)

        ctk.CTkLabel(parent, text="Activity Log", text_color=COLORS["text_dim"]).pack(anchor="w", pady=(10, 5))
        self.log_box = ctk.CTkTextbox(parent, fg_color=COLORS["card"])
        self.log_box.pack(fill="both", expand=True)

    def update_thread_lbl(self, value):
        self.lbl_threads.configure(text=f"Concurrent Threads: {int(value)}")

    def update_view_lbl(self, value):
        self.lbl_viewtime.configure(text=f"View Duration: {int(value)}s")

    def setup_proxy_ui(self, parent):
        tools = ctk.CTkFrame(parent, fg_color=COLORS["card"])
        tools.pack(fill="x", pady=(0, 10))

        # Row 1: Actions & Protocol Checkboxes
        r1 = ctk.CTkFrame(tools, fg_color="transparent")
        r1.pack(fill="x", padx=10, pady=10)

        ctk.CTkButton(r1, text="Scrape New", width=100, command=self.run_scraper).pack(side="left", padx=5)
        ctk.CTkButton(r1, text="Load File", width=100, fg_color=COLORS["accent"], command=self.load_proxy_file).pack(
            side="left", padx=5)
        ctk.CTkButton(r1, text="Export Active", width=100, fg_color="#F39C12", command=self.export_active).pack(
            side="right", padx=5)

        proto_frm = ctk.CTkFrame(tools, fg_color="transparent")
        proto_frm.pack(fill="x", padx=10, pady=5)

        self.chk_http = ctk.CTkCheckBox(proto_frm, text="HTTP/S", width=70)
        if self.settings.get("use_http", True): self.chk_http.select()
        self.chk_http.pack(side="left", padx=10)

        self.chk_socks4 = ctk.CTkCheckBox(proto_frm, text="SOCKS4", width=70)
        if self.settings.get("use_socks4", True): self.chk_socks4.select()
        self.chk_socks4.pack(side="left", padx=10)

        self.chk_socks5 = ctk.CTkCheckBox(proto_frm, text="SOCKS5", width=70)
        if self.settings.get("use_socks5", True): self.chk_socks5.select()
        self.chk_socks5.pack(side="left", padx=10)

        # NEW: Hide Dead Checkbox
        self.chk_hide_dead = ctk.CTkCheckBox(proto_frm, text="Hide Dead", width=70, fg_color=COLORS["danger"])
        if self.settings.get("hide_dead", True): self.chk_hide_dead.select()
        self.chk_hide_dead.pack(side="right", padx=10)

        r_counts = ctk.CTkFrame(tools, fg_color="transparent")
        r_counts.pack(fill="x", padx=10, pady=5)

        self.lbl_loaded = ctk.CTkLabel(r_counts, text="Total: 0", font=("Roboto", 12, "bold"))
        self.lbl_loaded.pack(side="left", padx=5)

        self.lbl_proto_counts = ctk.CTkLabel(r_counts, text="HTTP: 0 | SOCKS4: 0 | SOCKS5: 0",
                                             text_color=COLORS["text_dim"], font=("Roboto", 11))
        self.lbl_proto_counts.pack(side="right", padx=15)

        r2 = ctk.CTkFrame(tools, fg_color=COLORS["bg"])
        r2.pack(fill="x", padx=10, pady=(0, 10))

        self.entry_test_url = ctk.CTkEntry(r2, width=200, placeholder_text="Test Gateway")
        self.entry_test_url.insert(0, self.settings["proxy_test_url"])
        self.entry_test_url.pack(side="left", padx=5, pady=5)

        ctk.CTkLabel(r2, text="Timeout:").pack(side="left", padx=2)
        self.entry_timeout = ctk.CTkEntry(r2, width=40)
        self.entry_timeout.insert(0, str(self.settings["proxy_timeout"]))
        self.entry_timeout.pack(side="left", padx=2)

        ctk.CTkLabel(r2, text="Check Threads:").pack(side="left", padx=(10, 2))
        self.entry_check_threads = ctk.CTkEntry(r2, width=40)
        self.entry_check_threads.insert(0, str(self.settings["proxy_check_threads"]))
        self.entry_check_threads.pack(side="left", padx=2)

        ctk.CTkLabel(r2, text="Scrape Threads:").pack(side="left", padx=(10, 2))
        self.entry_scrape_threads = ctk.CTkEntry(r2, width=40)
        self.entry_scrape_threads.insert(0, str(self.settings["proxy_scrape_threads"]))
        self.entry_scrape_threads.pack(side="left", padx=2)

        self.btn_test = ctk.CTkButton(r2, text="TEST ALL", width=100, fg_color=COLORS["success"],
                                      command=self.toggle_test)
        self.btn_test.pack(side="right", padx=5, pady=5)

        self.progress_bar = ctk.CTkProgressBar(parent, height=10)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", pady=(0, 5))
        self.progress_bar.pack_forget()

        self.proxy_grid = VirtualGrid(parent, columns=["Address", "Proto", "Country", "Status", "Ping", "Anon"])
        self.proxy_grid.pack(fill="both", expand=True)

    def setup_settings_ui(self, parent):
        card = ctk.CTkFrame(parent, fg_color=COLORS["card"])
        card.pack(fill="x")
        self.chk_headless = ctk.CTkCheckBox(card, text="Headless Browser Mode (Invisible)")
        if self.settings.get("headless", True): self.chk_headless.select()
        self.chk_headless.pack(anchor="w", padx=20, pady=20)
        ctk.CTkButton(card, text="Save Configuration", command=self.save_cfg).pack(anchor="w", padx=20, pady=(0, 20))

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
                self.buffer = []
                self.proxy_grid.clear()

                with open(f, 'r') as file:
                    raw = [l.strip() for l in file if l.strip()]
                    self.proxies.extend(raw)

                self.update_proxy_stats()
                self.log(f"Cleared previous data. Loaded {len(raw)} proxies.")
            except:
                pass

    def export_active(self):
        active_objs = self.proxy_grid.get_active_objects()

        if not active_objs:
            return self.log("No active proxies to export.")

        if not os.path.exists("proxies"):
            os.makedirs("proxies")

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
                with open("proxies/socks.txt", "w") as f: f.write("\n".join(socks_list))
            if http_list:
                with open("proxies/http.txt", "w") as f: f.write("\n".join(http_list))

            self.log(f"Auto-Exported: {len(socks_list)} SOCKS, {len(http_list)} HTTP.")
        except Exception as e:
            self.log(f"Export Error: {e}")

    def run_scraper(self):
        try:
            th = int(self.entry_scrape_threads.get())
        except:
            th = 20

        protos = {
            "http": self.chk_http.get(),
            "socks4": self.chk_socks4.get(),
            "socks5": self.chk_socks5.get()
        }

        def _job():
            self.log(f"Scraping started with {th} threads...")
            found = ProxyEngine.scrape(self.settings["sources"], protos, max_threads=th)
            self.proxies.extend(found)
            self.proxies = list(set(self.proxies))

            self.after(0, self.update_proxy_stats)
            self.after(0, lambda: self.log(f"Scrape complete. Found {len(found)}."))

        threading.Thread(target=_job, daemon=True).start()

    def update_proxy_stats(self):
        total = len(self.proxies)
        self.lbl_loaded.configure(text=f"Total: {total}")
        counts = self.proxy_grid.get_counts()
        self.lbl_proto_counts.configure(
            text=f"HTTP: {counts['HTTP']} | SOCKS4: {counts['SOCKS4']} | SOCKS5: {counts['SOCKS5']}")

    def toggle_test(self):
        if self.testing:
            self.testing = False
            self.btn_test.configure(text="TEST ALL", fg_color=COLORS["success"])
        else:
            if not self.proxies: return self.log("Load proxies first.")
            self.testing = True
            self.btn_test.configure(text="STOP", fg_color=COLORS["danger"])
            self.proxy_grid.clear()
            threading.Thread(target=self.tester_thread, daemon=True).start()

    def tester_thread(self):
        self.progress_bar.pack(fill="x", pady=(0, 5))
        try:
            url = self.entry_test_url.get()
            to = int(self.entry_timeout.get())
            th = int(self.entry_check_threads.get())
            total = len(self.proxies)
            hide_dead = self.chk_hide_dead.get()

            allowed_protos = {
                "http": self.chk_http.get(),
                "socks4": self.chk_socks4.get(),
                "socks5": self.chk_socks5.get()
            }
        except:
            return

        self.log(f"Testing started with {th} threads (Timeout: {to}s)...")

        with ThreadPoolExecutor(max_workers=th) as ex:
            futures = [ex.submit(ProxyEngine.check, p, url, to, self.real_ip, allowed_protos) for p in self.proxies]

            for i, f in enumerate(futures):
                if not self.testing: break
                try:
                    res = f.result()

                    # PERFORMANCE: If Hide Dead is on and status is dead, skip buffering
                    if hide_dead and res["status"] != "Active":
                        continue

                    raw = res["proxy"].split("://")[-1]
                    ip, port = (raw.split(":")[0], raw.split(":")[1]) if ":" in raw else (raw, "")

                    self.buffer.append({
                        "ip": ip, "port": port, "type": res["type"],
                        "country": res["country"], "country_code": res["country_code"],
                        "status": res["status"], "speed": res["speed"], "anonymity": res["anonymity"]
                    })
                    prog = (i + 1) / total
                    self.after(0, lambda p=prog: self.progress_bar.set(p))
                except:
                    pass

        self.testing = False
        self.after(0, lambda: self.progress_bar.pack_forget())
        self.after(0, lambda: self.btn_test.configure(text="TEST ALL", fg_color=COLORS["success"]))
        self.after(0, lambda: self.log("Testing complete."))

    def toggle_attack(self):
        if self.running:
            self.running = False
            self.btn_attack.configure(text="START CAMPAIGN", fg_color=COLORS["success"])
        else:
            self.running = True
            self.btn_attack.configure(text="STOP CAMPAIGN", fg_color=COLORS["danger"])
            threading.Thread(target=self.attack_manager, daemon=True).start()

    def attack_manager(self):
        url = self.entry_url.get()
        threads = int(self.slider_threads.get())
        viewtime = int(self.slider_viewtime.get())

        self.log(f"Starting attack: {threads} threads on {url}")

        all_active = self.proxy_grid.get_active_objects()

        allowed = []
        if self.chk_http.get(): allowed.append("HTTP")
        if self.chk_http.get(): allowed.append("HTTPS")
        if self.chk_socks4.get(): allowed.append("SOCKS4")
        if self.chk_socks5.get(): allowed.append("SOCKS5")

        active_proxies = []
        for p in all_active:
            if any(a in p['type'] for a in allowed):
                active_proxies.append(f"{p['type'].lower()}://{p['ip']}:{p['port']}")

        if not active_proxies and all_active:
            self.log(f"Warning: Proxies active but filtered by protocol.")
        elif not active_proxies:
            self.log("No active proxies found.")

        def worker():
            ua = UserAgent()
            while self.running:
                try:
                    proxy_url = random.choice(active_proxies) if active_proxies else None
                    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
                    headers = {"User-Agent": ua.random}
                    r = requests.get(url, headers=headers, proxies=proxies, timeout=10)
                    if r.status_code == 200:
                        self.stats["success"] += 1
                        time.sleep(viewtime)
                    else:
                        self.stats["fail"] += 1
                except Exception:
                    self.stats["fail"] += 1
                self.stats["req"] += 1
                time.sleep(random.uniform(0.1, 1.0))

        pool = []
        for _ in range(threads):
            t = threading.Thread(target=worker, daemon=True)
            t.start()
            pool.append(t)

        while self.running:
            time.sleep(1)

    def save_cfg(self):
        try:
            self.settings["target_url"] = self.entry_url.get()
            self.settings["threads"] = int(self.slider_threads.get())
            self.settings["viewtime"] = int(self.slider_viewtime.get())
            self.settings["proxy_test_url"] = self.entry_test_url.get()
            self.settings["proxy_timeout"] = int(self.entry_timeout.get())
            self.settings["proxy_check_threads"] = int(self.entry_check_threads.get())
            self.settings["proxy_scrape_threads"] = int(self.entry_scrape_threads.get())
            self.settings["use_http"] = self.chk_http.get()
            self.settings["use_socks4"] = self.chk_socks4.get()
            self.settings["use_socks5"] = self.chk_socks5.get()
            self.settings["hide_dead"] = self.chk_hide_dead.get()
            self.settings["headless"] = self.chk_headless.get()
            Utils.save_settings(self.settings)
            self.log("Settings saved.")
        except Exception as e:
            self.log(f"Error saving settings: {e}")

    def update_gui_loop(self):
        if self.buffer:
            chunk = self.buffer[:40]
            del self.buffer[:40]
            for i in chunk: self.proxy_grid.add(i)
            if len(self.buffer) % 5 == 0: self.update_proxy_stats()

        self.lbl_stats["req"].configure(text=str(self.stats["req"]))
        self.lbl_stats["success"].configure(text=str(self.stats["success"]))
        self.lbl_stats["fail"].configure(text=str(self.stats["fail"]))

        self.after(100, self.update_gui_loop)


if __name__ == "__main__":
    app = ModernTrafficBot()
    app.mainloop()