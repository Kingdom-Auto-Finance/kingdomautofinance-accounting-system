"""
Supabase client for FastAPI backend.
"""
from supabase import create_client, Client
from app.core.config import settings


def get_supabase_client() -> Client:
    """
    Create and return a Supabase client instance.
    Uses service role key for admin access.
    """
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")

    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


# Singleton instance
supabase: Client = get_supabase_client()
