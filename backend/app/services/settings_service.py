"""
Settings service for managing system configuration.

Provides centralized settings management with:
- Database persistence in system_settings table
- In-memory caching with TTL
- Fallback to environment variables
- Google URL/ID extraction and validation
"""

import os
import re
import time
from typing import Optional, Dict
from supabase import Client
from app.core.supabase import get_supabase_client


class SettingsManager:
    """
    Manages system settings with caching and validation.

    Settings priority (highest to lowest):
    1. Database (system_settings table)
    2. Environment variables
    3. Provided default value
    """

    def __init__(self):
        self._cache: Dict[str, str] = {}
        self._cache_timestamp: Dict[str, float] = {}
        self._cache_ttl = 300  # 5 minutes in seconds
        self._supabase: Optional[Client] = None

    def _get_supabase(self) -> Client:
        """Get Supabase client (lazy initialization)"""
        if self._supabase is None:
            self._supabase = get_supabase_client()
        return self._supabase

    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached value is still valid based on TTL"""
        if key not in self._cache_timestamp:
            return False

        elapsed = time.time() - self._cache_timestamp[key]
        return elapsed < self._cache_ttl

    def get_setting(self, key: str, default: Optional[str] = None) -> str:
        """
        Get setting value with cache and fallback.

        Args:
            key: Setting key to retrieve
            default: Default value if not found in DB or env

        Returns:
            Setting value from DB, env, or default
        """
        # Check cache first
        if key in self._cache and self._is_cache_valid(key):
            return self._cache[key]

        try:
            # Try database
            supabase = self._get_supabase()
            response = supabase.table("system_settings").select("value").eq("key", key).single().execute()

            if response.data:
                value = response.data["value"]
                # Update cache
                self._cache[key] = value
                self._cache_timestamp[key] = time.time()
                return value
        except Exception as e:
            # Database error - fall through to environment variables
            print(f"Failed to get setting '{key}' from database: {e}")

        # Fallback to environment variable
        env_value = os.getenv(key)
        if env_value:
            return env_value

        # Final fallback to default
        if default is not None:
            return default

        raise ValueError(f"Setting '{key}' not found in database, environment, or provided default")

    def set_setting(self, key: str, value: str) -> Dict[str, str]:
        """
        Update setting in database and invalidate cache.

        Args:
            key: Setting key to update
            value: New value

        Returns:
            Dict with updated key and value
        """
        supabase = self._get_supabase()

        # Upsert into database
        response = supabase.table("system_settings").upsert({
            "key": key,
            "value": value
        }).execute()

        # Invalidate cache for this key
        if key in self._cache:
            del self._cache[key]
        if key in self._cache_timestamp:
            del self._cache_timestamp[key]

        return {"key": key, "value": value}

    def get_all_settings(self, category: Optional[str] = None) -> list:
        """
        Get all settings, optionally filtered by category.

        Args:
            category: Optional category to filter by

        Returns:
            List of setting dictionaries
        """
        supabase = self._get_supabase()

        query = supabase.table("system_settings").select("*")

        if category:
            query = query.eq("category", category)

        response = query.execute()
        return response.data if response.data else []

    def clear_cache(self):
        """Clear all cached settings"""
        self._cache.clear()
        self._cache_timestamp.clear()

    def extract_google_id(self, url_or_id: str, id_type: str) -> str:
        """
        Extract Google Sheet ID or Drive Folder ID from URL.
        Returns the ID if it's already in ID format.

        Args:
            url_or_id: Either a full Google URL or direct ID
            id_type: 'sheet' or 'folder'

        Returns:
            Extracted or validated ID

        Raises:
            ValueError: If URL/ID format is invalid
        """
        # Clean whitespace
        value = url_or_id.strip()

        if not value:
            raise ValueError("URL or ID cannot be empty")

        # Pattern for Google Sheet ID in URL
        if id_type == 'sheet':
            # Match: https://docs.google.com/spreadsheets/d/{ID}/...
            match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', value)
            if match:
                return match.group(1)

        # Pattern for Drive Folder ID in URL
        elif id_type == 'folder':
            # Match: https://drive.google.com/drive/folders/{ID}
            match = re.search(r'/folders/([a-zA-Z0-9-_]+)', value)
            if match:
                return match.group(1)
        else:
            raise ValueError(f"Invalid id_type: {id_type}. Must be 'sheet' or 'folder'")

        # If no URL pattern matched, validate if it's already a direct ID
        # Google IDs are alphanumeric with hyphens and underscores
        if re.match(r'^[a-zA-Z0-9-_]+$', value):
            # Validate length (Google IDs are typically 30-50 characters)
            if 10 <= len(value) <= 100:
                return value
            else:
                raise ValueError(f"ID length ({len(value)}) is unusual for Google {id_type} ID")

        # Neither URL nor valid ID format
        raise ValueError(
            f"Invalid Google {id_type} URL or ID format. "
            f"Expected URL like 'https://{'docs.google.com/spreadsheets/d/' if id_type == 'sheet' else 'drive.google.com/drive/folders/'}<ID>' "
            f"or direct ID (alphanumeric with hyphens/underscores)"
        )


# Singleton instance (imported by settings_manager.py)
settings_manager = SettingsManager()
