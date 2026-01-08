"""
Configuration management for FastAPI backend.
Reuses existing configuration from src/config.py
"""
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # API Settings
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "Kingdom Auto Finance API"
    VERSION: str = "1.0.0"

    # Supabase
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    # Google Cloud
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    GOOGLE_CREDENTIALS_JSON: Optional[str] = os.getenv("GOOGLE_CREDENTIALS_JSON")

    # Google Sheets
    GOOGLE_SHEETS_FOLDER_ID: str = os.getenv("GOOGLE_SHEETS_FOLDER_ID", "")
    GOOGLE_SHEETS_SOURCE_ID: str = os.getenv("GOOGLE_SHEETS_SOURCE_ID", "")

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:8501",
        "https://accounting.kingdomautofinance.com",
    ]

    class Config:
        case_sensitive = True
        env_file = ".env"


settings = Settings()
