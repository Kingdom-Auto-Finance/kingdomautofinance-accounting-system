"""
Supabase client for FastAPI backend.
"""
from supabase import create_client, Client
from typing import Optional

_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """
    Get or create Supabase client instance (lazy-loaded singleton).
    Uses service role key for admin access.
    """
    global _supabase_client

    if _supabase_client is None:
        from app.core.config import settings

        if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")

        _supabase_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

    return _supabase_client


# For backward compatibility with "from app.db.supabase_client import supabase"
class _SupabaseAccessor:
    def __getattr__(self, name):
        return getattr(get_supabase_client(), name)


supabase = _SupabaseAccessor()
