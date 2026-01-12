"""
Base page abstract class for DarkMatter Traffic Bot UI pages.

This module provides a standard interface for page initialization,
state management, and lifecycle hooks, enabling decoupling between
pages and the main application.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

if TYPE_CHECKING:
    from ..app import ModernTrafficBot


class BasePage(ABC):
    """Abstract base class for UI pages.

    Provides a standard interface for page initialization, state management,
    and lifecycle hooks.
    """

    def __init__(self, app: "ModernTrafficBot"):
        """Initialize the page.

        Args:
            app: The main application instance for shared state access.
        """
        self.app = app

    @abstractmethod
    def setup(self, parent: ctk.CTkFrame) -> None:
        """Set up the page UI in the parent frame.

        Args:
            parent: The parent frame to build the UI in.
        """

    @abstractmethod
    def get_state(self) -> dict[str, Any]:
        """Get the current state of the page widgets.

        Returns:
            dict: A dictionary containing the current values of interactive widgets.
        """

    @abstractmethod
    def set_state(self, state: dict[str, Any]) -> None:
        """Set the state of the page widgets.

        Args:
            state: A dictionary containing values to apply to widgets.
        """

    def on_show(self) -> None:  # noqa: B027
        """Lifecycle hook called when the page becomes visible.

        Override this method to perform actions when the user navigates to this page.
        Default implementation does nothing.
        """

    def on_hide(self) -> None:  # noqa: B027
        """Lifecycle hook called when the page is hidden.

        Override this method to perform actions when the user leaves this page.
        Default implementation does nothing.
        """
