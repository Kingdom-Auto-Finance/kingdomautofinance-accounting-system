"""
Settings manager singleton.

This module provides a single instance of SettingsManager
that can be imported throughout the application.
"""

from app.services.settings_service import settings_manager

# Export the singleton instance
__all__ = ['settings_manager']
