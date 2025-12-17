# Project To-Do & Recommendations

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

### Proxy Checking Enhancement
- [ ] **Full proxy chaining** - Route checks through system proxy to hide IP from proxy operators (requires SOCKS5 tunneling)

---

## Backlog

### Codebase Structure & Quality
- [ ] **Standardize Testing:** Move `resources/tests` to a top-level `tests/` directory and integrate `pytest`
- [ ] **Linting & Formatting:** Create `dev-requirements.txt` (black, pylint) for code style enforcement
- [ ] **Unit tests for validation functions**

### Traffic Realism Features
- [ ] **Configurable Referers:** Externalize referers to `resources/referers.txt` or UI setting
- [ ] **Scenario Mode:** Visit profiles that hit target, wait, then visit sub-pages

### Proxy Management
- [ ] **Source Health Tracking:** Track success rates of URLs in `sources.txt`, auto-disable dead sources
- [ ] **Auto-Update Sources:** Fetch fresh `sources.txt` from remote repository

### User Interface & Logging
- [ ] **File-Based Logging:** Optional file logging with rotation for debugging long sessions
- [ ] **Session Export:** Export session statistics (Success/Fail/Proxy Count) to CSV/JSON

---

## Known Issues (Resolved)

### Traffic Attack Module (Fixed in v3.2.0)
- [x] ~~**TLS/Header Mismatch:** curl_cffi impersonations mixed with unrelated User-Agents~~ - Removed HeaderManager randomization
- [x] ~~**Session Reuse:** TLS sessions/cookies reused across simulated users~~ - Fresh AsyncSession per task
- [x] ~~**Accept Header:** Fallback `Accept: */*` suspicious for browser traffic~~ - Proper browser headers

---

## Extra Notes
- [x] ~~Notification when proxy scraping finished~~ - Added popup notification
- [x] ~~Make UI elements dynamically scalable~~ - Grid layout implemented
- [ ] Optional file-based logging with rotation
- [ ] Additional proxy source management features
