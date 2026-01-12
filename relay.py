#!/usr/bin/env python3
"""
DarkMatter Traffic Bot - Relay Server

Standalone relay server for routing messages between Controller and Agents.
Enables NAT traversal by having both sides connect outbound to the relay.

Usage:
    python relay.py --port 8765 --secret "your-secret-key"
    python relay.py  # Uses environment variables

Environment Variables:
    DM_RELAY_HOST       Bind address (default: 0.0.0.0)
    DM_RELAY_PORT       Relay server port (default: 8765)
    DM_SECRET_KEY       Shared authentication secret (min 32 chars)
    DM_LOG_LEVEL        Logging level (DEBUG, INFO, WARNING, ERROR)
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

# Ensure project root is in path for imports
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.relay_server import RelayServer  # noqa: E402


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure logging for systemd (stdout only)."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    logger = logging.getLogger("dm-relay")
    logger.setLevel(log_level)

    return logger


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="DarkMatter Relay Server - Routes messages between Controller and Agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python relay.py --port 8765 --secret "your-32-char-secret-key-here!!!"
    python relay.py --host 0.0.0.0 --port 9000

Environment Variables:
    DM_RELAY_HOST       Bind address (default: 0.0.0.0)
    DM_RELAY_PORT       Relay server port (default: 8765)
    DM_SECRET_KEY       Shared authentication secret
    DM_LOG_LEVEL        Logging level (DEBUG, INFO, WARNING, ERROR)
        """,
    )

    parser.add_argument(
        "--host",
        "-H",
        default=os.environ.get("DM_RELAY_HOST", "0.0.0.0"),
        help="Bind address (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=int(os.environ.get("DM_RELAY_PORT", "8765")),
        help="Relay server port (default: 8765)",
    )
    parser.add_argument(
        "--secret",
        "-s",
        default=os.environ.get("DM_SECRET_KEY", ""),
        help="Authentication secret (min 32 chars). Use env var DM_SECRET_KEY for security.",
    )
    parser.add_argument(
        "--log-level",
        "-l",
        default=os.environ.get("DM_LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    return parser.parse_args()


class RelayApplication:
    """Main relay application with signal handling."""

    def __init__(self, host: str, port: int, secret_key: str, logger: logging.Logger):
        self.host = host
        self.port = port
        self.secret_key = secret_key
        self.logger = logger
        self.server: RelayServer | None = None
        self._shutdown_event = asyncio.Event()

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._handle_signal, sig)
            except NotImplementedError:
                pass  # Windows

    def _handle_signal(self, sig: signal.Signals):
        """Handle shutdown signal."""
        self.logger.info(f"Received {sig.name}, initiating shutdown...")
        self._shutdown_event.set()

    async def run(self):
        """Main application loop."""
        self._setup_signal_handlers()

        # Create relay server
        self.server = RelayServer(
            host=self.host,
            port=self.port,
            secret_key=self.secret_key,
            on_log=lambda msg: self.logger.info(msg),
        )

        self.logger.info("=" * 60)
        self.logger.info("DarkMatter Relay Server Starting")
        self.logger.info("=" * 60)
        self.logger.info(f"Bind Address: {self.host}:{self.port}")
        self.logger.info(f"WebSocket URL: ws://{self.host}:{self.port}/ws")
        self.logger.info("=" * 60)

        try:
            # Start server
            await self.server.start()

            # Wait for shutdown signal
            await self._shutdown_event.wait()

        except Exception as e:
            self.logger.error(f"Server error: {e}", exc_info=True)
        finally:
            if self.server:
                await self.server.stop()
            self.logger.info("Relay server stopped")


async def main():
    """Main entry point."""
    args = parse_args()
    logger = setup_logging(args.log_level)

    # Validate secret key
    if not args.secret or len(args.secret) < 32:
        logger.error("Secret key must be at least 32 characters")
        logger.error("Use --secret or set DM_SECRET_KEY environment variable")
        sys.exit(1)

    app = RelayApplication(
        host=args.host,
        port=args.port,
        secret_key=args.secret,
        logger=logger,
    )

    try:
        await app.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
