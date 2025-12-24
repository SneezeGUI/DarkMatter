# Project To-Do & Recommendations

## Completed (v3.6.0+)

### UI/UX Improvements (2025-12-17)
- [x] **Clear Dead button** - Remove dead proxies without clearing active ones
- [x] **Activity log auto-scroll** - Minimum height, thread-safe logging, reliable scroll behavior
- [x] **Adjustable column widths** - Proxy list columns resizable by dragging header edges
- [x] **Pinned progress bar** - Progress bar stays visible, no more layout jumping
- [x] **Unique proxy per thread** - Traffic engine assigns unique proxies to concurrent tasks

### Browser Fingerprint (2025-12-17)
- [x] **OS Emulation profiles** - 6 profiles (Win/Mac/Linux × Chrome/Firefox/Safari/Edge)
- [x] **Fingerprint uniqueness** - Canvas, AudioContext, ClientRect, performance.now() noise per session
- [x] **Fingerprint rotation** - Auto-rotate after 50 requests or 30 minutes (configurable)
- [x] **Engine activity logging** - Browser/curl engine events now show in GUI activity log

### Cloudflare Bypass Improvements (2025-12-17)
- [x] **Enhanced detection markers** - 20+ markers with confidence scoring and title matching
- [x] **Multi-stage bypass strategy** - 4-stage approach: JS wait, human simulation, checkbox click, API solve
- [x] **Cookie-based verification** - cf_clearance cookie + content analysis for reliable success detection
- [x] **Turnstile iframe handling** - Extracts sitekey from iframes, attempts checkbox clicks
- [x] **Human behavior simulation** - Mouse movements, scrolling, randomized click offsets
- [x] **Detailed bypass logging** - Stage-by-stage progress with timing in activity log
- [x] **Double verification** - Post-bypass verification before counting as success

### Export System (2025-12-17)
- [x] **Folder selection dialog** - Prompts for export folder if not set in settings
- [x] **Category export buttons** - All, HTTP, HTTPS, SOCKS buttons (color-coded)
- [x] **Protocol toggle** - Checkbox to include/exclude protocol prefix (http://, socks5://)

### Bug Fixes (2025-12-17)
- [x] **Request/Success counter mismatch** - Moved `total_requests++` to start of request (guarantees req >= success+failed)
- [x] **Success count accuracy** - Double-verification after CF bypass before counting
- [x] **CaptchaProvider enum error** - Fixed `get_available_providers()` to return strings instead of enum objects

### New Features (2025-12-20)
- [x] **Protocol color coding** - HTTP (blue), HTTPS (purple), SOCKS4 (dark teal), SOCKS5 (teal) in proxy list
- [x] **Configurable referers** - Load from `resources/referers.txt` with fallback to defaults
- [x] **Traffic pattern randomization** - Burst mode with configurable requests per burst and sleep intervals
- [x] **Responsive UI** - Scrollable config areas for small screens (960x540), minsize 800x500
- [x] **DPI Scaling** - Scale-aware UI elements (sidebar, buttons, fonts, grid rows) for high-DPI displays
- [x] **Draggable activity log** - Resizable panels via DraggableSash component (Dashboard & Stress Test)
- [x] **Two-phase proxy checking** - Only check validators after proxy confirmed alive (saves bandwidth)

### Bug Fixes (2025-12-20)
- [x] **Export button scaling** - Fixed export proxy buttons not scaling with DPI
- [x] **VirtualGrid column resize** - Fixed header/content misalignment when resizing columns
- [x] **CTk place() limitation** - Fixed ValueError by using configure() for widget dimensions
- [x] **GeoIP fallbacks** - Improved fallback chain and increased API timeouts

---

## Completed (v3.4.0)

### Multi-Validator Anonymity System
- [x] **Multi-validator proxy checking** - 6 built-in validators (httpbin, ip-api, ipify, ipinfo, azenv, wtfismyip)
- [x] **Anonymity scoring (0-100)** - Aggregated results from multiple endpoints
- [x] **Validator selection UI** - Checkbox list in Settings with test depth (Quick/Normal/Thorough)
- [x] **Header leak detection** - Checks 20+ IP-exposing headers and 17+ proxy-revealing headers

### Proxy Persistence & Management
- [x] **Proxy persistence between sessions** - Active proxies saved to `resources/proxies.json`
- [x] **Auto-save during testing** - Saves every 25 active proxies found
- [x] **Save on STOP/Close** - Proxies saved when stopping test or closing app
- [x] **Clipboard import** - Import proxies from clipboard with deduplication
- [x] **Scrape deduplication** - New scrapes skip already-checked proxies
- [x] **Clear All button** - Clears proxies from memory and disk

### GeoIP & Display
- [x] **MaxMind GeoLite2 local database** - Bundled 60MB database for fast lookups
- [x] **API fallback** - Falls back to ip-api.com when local lookup fails
- [x] **Country display fix** - Text-based `[CC] City` format (Tkinter doesn't render emoji flags)
- [x] **Anonymity counters** - Shows Elite/Anonymous/Transparent/Unknown counts

### UI Improvements
- [x] **Dashboard grid layout** - Scalable layout with browser stats above activity log
- [x] **Separate captcha balances** - Shows 2captcha and AntiCaptcha balances separately
- [x] **System proxy** - Renamed from "Scraper Proxy" with separate Scrape/Check toggles
- [x] **Grid auto-sort** - Re-sorts every 10 items to maintain order during testing
- [x] **Boolean casting fix** - Fixed browser headless parameter (was number, expected boolean)

---

## In Progress

### v3.7.0 Master/Slave Architecture
- [x] **Phase 1: Communication Layer** - WebSocket server/client with HMAC authentication *(2025-12-23)*
- [ ] **Phase 2: Headless Client** - `slave.py` entry point for Linux nodes
- [ ] **Phase 3: Master GUI Components** - Master control page and scanner results
- [ ] **Phase 4: SSH/RDP Scanner** - Network scanning capabilities
- [ ] **Phase 5: Linux Deployment** - systemd service and Ansible playbooks
- [ ] **Phase 6: Integration & Testing** - End-to-end verification

---

## Completed (v3.6.3 - 2025-12-23)

### Code Quality & v3.7.0 Preparation
- [x] **Fixed 185+ linting errors** - Type annotations, import sorting, unused variables, try-except patterns
- [x] **All linting clean** - 0 ruff errors, modern Python type syntax
- [x] **Proxy chaining preparation** - Added `system_proxy` parameter for future SOCKS5 tunneling
- [x] **Documentation** - CLAUDE.MD project context, v3.7.0-plan.md (1,745 lines)
- [x] **WebSocket dependencies** - Added websockets>=12.0 and asyncssh>=2.14.0

## Completed (v3.6.5 - 2025-12-22)

### Foundation & Testing
- [x] **Testing Infrastructure:** Added `tests/` directory with `pytest` and `pytest-asyncio`
- [x] **Unit Tests:** Implemented tests for Models, Utils, and Configuration (100% pass)
- [x] **Config Env Vars:** Implemented `DM_*` environment variable overrides for Linux slave support
- [x] **Bug Fixes:** Fixed `ProxyConfig` serialization and `deduplicate_proxies` whitespace handling

---

## Completed (v3.6.1+ Refactor - 2025-12-21)

### Codebase Structure & Quality
- [x] **Split ui/app.py:** Modular page architecture with `ui/pages/` directory
  - `ui/pages/dashboard.py` - Dashboard page (~500 lines)
  - `ui/pages/proxy_manager.py` - Proxy Manager page (~350 lines)
  - `ui/pages/stress_test.py` - Stress Test page (~360 lines)
  - `ui/pages/settings.py` - Settings page (~350 lines)
  - `ui/scaling.py` - DPI scaling utilities
  - Widget binding methods for backward compatibility
- [x] **Linting & Formatting:** Full dev tooling setup
  - `dev-requirements.txt` (black, ruff, mypy, pytest, pre-commit)
  - `pyproject.toml` with Black, Ruff, MyPy, Pytest configuration
  - All files pass Black formatting and Ruff linting
  - Fixed 27 linting issues in app.py (imports, unused vars, closure bugs, duplicates)

---

## Backlog

### v3.7.0 Master/Slave (In Progress - See "In Progress" section above)
- [x] **Communication Layer:** WebSocket with HMAC authentication *(Phase 1 Complete)*
- [ ] **Headless Client:** `slave.py` for Linux nodes *(Phase 2)*
- [ ] **Master GUI:** `ui/pages/master_control.py` for managing slaves *(Phase 3)*
- [ ] **Scanner Module:** SSH/RDP detection and credential testing *(Phase 4)*
- [ ] **Deployment:** systemd service files and install scripts *(Phase 5)*

### Codebase Structure & Quality
- [ ] **Standardize Testing:** Add more tests for engine logic and validators
- [ ] **Pre-commit hooks:** Set up pre-commit with black/ruff

### Traffic Realism Features
- [x] **Traffic pattern randomization:** Burst/sleep patterns for more realistic traffic profiles *(v3.6.1)*
- [x] **Configurable Referers:** Externalize referers to `resources/referers.txt` *(v3.6.1)*
- [ ] **Session cookie persistence:** Maintain cookies across runs for session continuity
- [ ] **Scenario Mode:** Visit profiles that hit target, wait, then visit sub-pages

### Proxy Management
- [x] **Protocol color coding:** Color code protocol category in proxy checker results *(v3.6.1)*
- [ ] **Source Health Tracking:** Track success rates of URLs in `sources.txt`, auto-disable dead sources
- [ ] **Auto-Update Sources:** Fetch fresh `sources.txt` from remote repository
- [ ] **Center Value/Text** center value/text in each resizable results column for proxy manager
### User Interface & Logging
- [ ] **File-Based Logging:** Optional file logging with rotation for debugging long sessions
- [ ] **Session Export:** Export session statistics (Success/Fail/Proxy Count) to CSV/JSON

### Master/Slave & Security Features (v3.7.0)
- [x] **Key Exchange:** HMAC-SHA256 authentication with challenge-response *(Phase 1 Complete)*
- [x] **Data Sync:** WebSocket communication layer with message routing *(Phase 1 Complete)*
- [x] **Testing:** 15 WebSocket tests covering auth, messaging, heartbeat, reconnection *(Phase 1 Complete)*
- [ ] **Headless Client:** Develop CLI (`slave.py`) for proxy scraping and IP/port scanning *(Phase 2)*
- [ ] **SSH/RDP Scanner:** Integrate modules for SSH/RDP detection and credential scanning *(Phase 4)*
- [ ] **Master GUI:** Design separate page for discovered SSH/RDP servers *(Phase 3)*
- [ ] **Error Handling:** Implement robust error reporting and retry mechanisms *(Phase 6)*
- [ ] **Configuration:** Define master/slave configuration parameters in Settings *(Phase 3)*
- [ ] **Deployment:** systemd service files, install scripts, Ansible playbooks *(Phase 5)*

---

## Known Issues (Resolved)

### Traffic Attack Module (Fixed in v3.2.0)
- [x] ~~**TLS/Header Mismatch:** curl_cffi impersonations mixed with unrelated User-Agents~~ - Removed HeaderManager randomization
- [x] ~~**Session Reuse:** TLS sessions/cookies reused across simulated users~~ - Fresh AsyncSession per task
- [x] ~~**Accept Header:** Fallback `Accept: */*` suspicious for browser traffic~~ - Proper browser headers

---

## Historical Notes (Completed)
- [x] ~~Notification when proxy scraping finished~~ - Added popup notification
- [x] ~~Make UI elements dynamically scalable~~ - Grid layout implemented
- [x] ~~Setup Proper OS Emulation/Spoofing~~ - OS profiles with consistent navigator properties, Client Hints, WebGL spoofing
- [x] ~~Export folder selection~~ - Prompts for folder selection, saves to settings
- [x] ~~Category export buttons~~ - Export buttons: All, HTTP, HTTPS, SOCKS with protocol toggle
