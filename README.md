# DarkMatter Traffic Bot (DM-Trafficbot)

**Version 3.6.0**

DM-Trafficbot is a sophisticated, high-performance traffic generation, proxy validation, and security testing tool. It combines human emulation (Browser/TLS fingerprinting) with authorized stress testing capabilities, designed for security researchers, QA teams, and developers.

## Core Features

### 1. Triple Engine Architecture
DM-Trafficbot employs three distinct engines for different use cases:
-   **Async Traffic Engine (Fast):** Uses `curl_cffi` to mimic real browser TLS signatures (Chrome, Safari, etc.), bypassing sophisticated bot detection systems with high concurrency and low overhead.
-   **Browser Engine (Realistic):** Integrates `playwright` (Chromium) to execute full JavaScript, bypassing complex challenges like Cloudflare Turnstile and handling dynamic content.
-   **Stress Engine (Load Test):** A specialized async engine for authorized security testing using HTTP proxies.

### 2. Advanced Proxy Manager
A powerhouse for proxy validation and management, supporting up to 10,000 concurrent threads.
-   **Protocols:** HTTP, HTTPS, SOCKS4, SOCKS5 (with authentication).
-   **Anonymity System:** Multi-validator system to classify proxies as Transparent, Anonymous, or Elite.
-   **GeoIP Integration:** Deep geolocation data (City, ISP, Country) using local MaxMind DB with API fallbacks.
-   **Sources:** Built-in list of 60+ reliable proxy sources.
-   **Filtering:** Filter by protocol, country, anonymity, and latency.

### 3. Stress Testing (New in v3.6.0)
**⚠️ Authorized Security Testing Only.**
A dedicated tab for load testing your own infrastructure using massive lists of HTTP proxies (~55,000+ supported).
-   **Attack Types:**
    -   **HTTP Flood:** High-volume GET/POST/HEAD/PUT/DELETE requests.
    -   **Slowloris:** Exhausts server connections with slow partial headers.
    -   **RUDY (R-U-Dead-Yet):** Slow POST body attacks.
    -   **Randomized:** A mix of all attack types to simulate chaotic load.
-   **Real-time Stats:** Monitor RPS, latency, success/fail rates, and active proxies.
-   **Safety:** Built-in safeguards, confirmation dialogs, and auto-stop limits.

### 4. Protection Bypass
-   **TLS Fingerprinting:** Mimics Chrome 120+, Safari, and other modern browsers.
-   **Captcha Solving:** Integration with 2Captcha and AntiCaptcha APIs.
-   **Cloudflare/Akamai:** Browser engine capability to handle JS challenges.

## User Interface
The application features a modern, dark-themed UI built with `customtkinter`.
-   **🚀 Dashboard:** Manage traffic campaigns and view live stats.
-   **🛡️ Proxy Manager:** Scrape, test, and filter proxies with a virtualized high-performance grid.
-   **💥 Stress Test:** dedicated load testing interface.
-   **⚙️ Settings:** Comprehensive configuration for engines, timeouts, and preferences.

## Getting Started

### Prerequisites
-   Python 3.10+
-   A virtual environment is strongly recommended.

### Installation & Running from Source
1.  **Set up Virtual Environment**:
    ```sh
    python -m venv .venv
    .venv\Scripts\activate  # Windows
    source .venv/bin/activate # Linux/Mac
    ```
2.  **Install Dependencies**:
    ```sh
    pip install -r requirements.txt
    playwright install chromium # Required for Browser Engine
    ```
3.  **Run the Application**:
    ```sh
    python main.py
    ```

### Building the Executable
You can build a standalone `.exe` file for easy distribution. The build script automatically enforces the virtual environment and bundles all assets.

1.  **Run the Build Script**:
    ```sh
    python build.py
    ```
2.  **Locate the Output**:
    The build script will generate a zip file `DarkMatterBot_v3.6.0.zip` in the root directory, containing the standalone executable.

## Disclaimer
This tool is intended for **educational and legitimate testing purposes only**. The developers assume no liability and are not responsible for any misuse or damage caused by this program. Using this tool against websites or servers without prior mutual consent is illegal. Always obtain authorization before performing stress tests.
