"""UI page modules for DarkMatter Traffic Bot.

Each page module contains the UI setup and event handlers for a specific tab.
"""

from .dashboard import DashboardPage
from .master_control import MasterControlPage
from .proxy_manager import ProxyManagerPage
from .settings import SettingsPage
from .stress_test import StressTestPage

__all__ = [
    "DashboardPage",
    "MasterControlPage",
    "ProxyManagerPage",
    "StressTestPage",
    "SettingsPage",
]
