#!/usr/bin/env python3
"""
DarkMatter Traffic Bot - Slave Node

Headless client for distributed traffic generation and proxy management.
Designed for Linux servers running under systemd.

Usage:
    python slave.py --master 192.168.1.100:8765 --name slave-01
    python slave.py --mode relay --master relay.example.com:8765
    python slave.py  # Uses environment variables

Connection Modes:
    direct      Connect directly to Master (LAN or port-forwarded)
    relay       Connect to Relay server (NAT traversal, recommended for WAN)
    cloudflare  Connect via Cloudflare Tunnel (master_host is tunnel URL)

Environment Variables:
    DM_MASTER_HOST      Master/Relay server hostname/IP (or Cloudflare URL)
    DM_MASTER_PORT      Master/Relay server port (default: 8765)
    DM_SECRET_KEY       Shared authentication secret (min 32 chars)
    DM_SLAVE_NAME       This node's identifier
    DM_CONNECTION_MODE  Connection mode: direct, relay, cloudflare (default: direct)
    DM_LOG_LEVEL        Logging level (DEBUG, INFO, WARNING, ERROR)
"""

import argparse
import asyncio
import contextlib
import logging
import os
import signal
import sys
from pathlib import Path

# Ensure project root is in path for imports
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.slave_controller import SlaveController  # noqa: E402
from ui.utils import Utils  # noqa: E402


def setup_logging(level: str = "INFO") -> logging.Logger:
    """
    Configure logging for systemd (stdout only).

    systemd captures stdout/stderr to journalctl automatically.
    View logs: journalctl -u dm-slave -f
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format="%(levelname)-8s | %(name)-20s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Get our logger
    logger = logging.getLogger("dm-slave")
    logger.setLevel(log_level)

    return logger


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="DarkMatter Slave Node - Headless traffic generation client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python slave.py --master 192.168.1.100:8765 --name slave-01
    python slave.py --master master.example.com:8765 --secret "your-secret-key"

Environment Variables:
    DM_MASTER_HOST      Master server hostname/IP
    DM_MASTER_PORT      Master server port (default: 8765)
    DM_SLAVE_SECRET     Shared authentication secret
    DM_SLAVE_NAME       This node's identifier
    DM_LOG_LEVEL        Logging level (DEBUG, INFO, WARNING, ERROR)
        """,
    )

    parser.add_argument(
        "--master",
        "-m",
        metavar="HOST:PORT",
        help="Master server address (e.g., 192.168.1.100:8765)",
    )
    parser.add_argument(
        "--name",
        "-n",
        metavar="NAME",
        help="Slave node name (default: slave-01)",
    )
    parser.add_argument(
        "--secret",
        "-s",
        metavar="KEY",
        help="Authentication secret (min 32 chars). Use env var DM_SLAVE_SECRET for security.",
    )
    parser.add_argument(
        "--log-level",
        "-l",
        default=os.environ.get("DM_LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--config",
        "-c",
        metavar="FILE",
        help="Config file path (default: resources/settings.json)",
    )
    parser.add_argument(
        "--mode",
        "-M",
        default=os.environ.get("DM_CONNECTION_MODE", "direct"),
        choices=["direct", "relay", "cloudflare"],
        help="Connection mode: direct (LAN), relay (via relay server), cloudflare (via tunnel)",
    )

    return parser.parse_args()


def validate_settings(settings: dict, logger: logging.Logger) -> bool:
    """Validate required settings are present."""
    errors = []

    if not settings.get("master_host"):
        errors.append("Master host not specified. Use --master or DM_MASTER_HOST")

    if not settings.get("slave_secret_key"):
        errors.append("Secret key not specified. Use --secret or DM_SLAVE_SECRET")
    elif len(settings.get("slave_secret_key", "")) < 32:
        errors.append("Secret key must be at least 32 characters")

    if not settings.get("slave_name"):
        errors.append("Slave name not specified. Use --name or DM_SLAVE_NAME")

    for error in errors:
        logger.error(error)

    return len(errors) == 0


def build_settings(args: argparse.Namespace, logger: logging.Logger) -> dict:
    """
    Build settings from file, environment, and CLI arguments.

    Priority (highest to lowest):
    1. CLI arguments
    2. Environment variables (DM_*)
    3. Config file
    4. Defaults
    """
    # Load base settings (handles env vars internally)
    config_file = args.config or "resources/settings.json"
    settings = Utils.load_settings(config_file)

    # CLI overrides (highest priority)
    if args.master:
        try:
            if ":" in args.master:
                host, port = args.master.rsplit(":", 1)
                settings["master_host"] = host
                settings["master_port"] = int(port)
            else:
                settings["master_host"] = args.master
        except ValueError:
            logger.error(f"Invalid master address format: {args.master}")

    if args.name:
        settings["slave_name"] = args.name

    if args.secret:
        settings["slave_secret_key"] = args.secret

    # Connection mode
    settings["connection_mode"] = args.mode

    return settings


class SlaveApplication:
    """Main slave application with signal handling and lifecycle management."""

    def __init__(self, settings: dict, logger: logging.Logger):
        self.settings = settings
        self.logger = logger
        self.controller: SlaveController | None = None
        self._shutdown_event = asyncio.Event()

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._handle_signal, sig)
                self.logger.debug(f"Registered handler for {sig.name}")
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                self.logger.debug(f"Signal handler not supported for {sig.name}")

    def _handle_signal(self, sig: signal.Signals):
        """Handle shutdown signal."""
        self.logger.info(f"Received {sig.name}, initiating graceful shutdown...")
        self._shutdown_event.set()

    async def run(self):
        """Main application loop."""
        self._setup_signal_handlers()

        # Get connection mode
        connection_mode = self.settings.get("connection_mode", "direct")

        # Create controller
        self.controller = SlaveController(
            master_host=self.settings["master_host"],
            master_port=self.settings.get("master_port", 8765),
            secret_key=self.settings["slave_secret_key"],
            slave_name=self.settings.get("slave_name", "slave-01"),
            settings=self.settings,
            connection_mode=connection_mode,
        )

        self.logger.info("=" * 60)
        self.logger.info("DarkMatter Slave Node Starting")
        self.logger.info("=" * 60)
        self.logger.info(f"Slave Name: {self.settings.get('slave_name', 'slave-01')}")
        self.logger.info(f"Connection Mode: {connection_mode}")
        if connection_mode == "cloudflare":
            self.logger.info(f"Tunnel URL: {self.settings['master_host']}")
        else:
            self.logger.info(
                f"Server: {self.settings['master_host']}:{self.settings.get('master_port', 8765)}"
            )
        self.logger.info("=" * 60)

        try:
            # Run controller and wait for shutdown
            controller_task = asyncio.create_task(self.controller.run())
            shutdown_task = asyncio.create_task(self._shutdown_event.wait())

            # Wait for either shutdown signal or controller to stop
            done, pending = await asyncio.wait(
                [controller_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # If shutdown was triggered, stop controller
            if shutdown_task in done:
                self.logger.info("Shutdown signal received, stopping controller...")
                await self.controller.stop()

                # Wait for controller to finish (with timeout)
                if controller_task in pending:
                    try:
                        await asyncio.wait_for(controller_task, timeout=10.0)
                    except asyncio.TimeoutError:
                        self.logger.warning("Controller shutdown timed out, cancelling...")
                        controller_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await controller_task

        except asyncio.CancelledError:
            self.logger.info("Application cancelled")
        except Exception as e:
            self.logger.error(f"Fatal error: {e}", exc_info=True)
            raise
        finally:
            await self._cleanup()

    async def _cleanup(self):
        """Cleanup resources."""
        self.logger.info("Cleaning up...")

        if self.controller:
            await self.controller.cleanup()

        self.logger.info("Shutdown complete")


async def main():
    """Main entry point."""
    # Parse arguments
    args = parse_args()

    # Setup logging
    logger = setup_logging(args.log_level)

    # Build settings
    settings = build_settings(args, logger)

    # Validate settings
    if not validate_settings(settings, logger):
        logger.error("Configuration validation failed. Exiting.")
        sys.exit(1)

    # Create and run application
    app = SlaveApplication(settings, logger)

    try:
        await app.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # Handle Windows-specific event loop policy
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
