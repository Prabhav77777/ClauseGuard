"""Application configuration loaded from environment variables.

All settings are loaded via pydantic-settings from .env or environment variables.
No secrets are ever hardcoded. The API key is validated at startup when needed,
not during module import, to allow tests to run without a key.
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """ClauseGuard application settings.
    
    Loaded from environment variables or .env file.
    See .env.example for documentation of each setting.
    """
    # Gemini API key (supports GEMINI_API_KEY or GOOGLE_API_KEY env vars)
    GEMINI_API_KEY: str = ""
    
    # Document limits
    MAX_FILE_SIZE_MB: int = 10
    MAX_PAGES: int = 50
    MAX_CHARACTERS: int = 500000
    
    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 10
    RATE_LIMIT_PERIOD: str = "minute"
    
    # Session management
    SESSION_TTL_SECONDS: int = 3600
    
    # Gemini model selection
    GEMINI_MODEL: str = "gemini-2.5-flash"
    
    # Logging — only metadata, never document content
    LOG_LEVEL: str = "INFO"
    
    # CORS origins for frontend
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

    model_config = SettingsConfigDict(
        env_file=".env" if os.path.exists(".env") else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Fallback to GOOGLE_API_KEY if GEMINI_API_KEY is not set
        if not self.GEMINI_API_KEY:
            self.GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

    def __repr__(self) -> str:
        masked_key = "***" if self.GEMINI_API_KEY else ""
        return (
            f"Settings(GEMINI_MODEL='{self.GEMINI_MODEL}', "
            f"MAX_FILE_SIZE_MB={self.MAX_FILE_SIZE_MB}, "
            f"GEMINI_API_KEY='{masked_key}')"
        )

    def __str__(self) -> str:
        return self.__repr__()


# Module-level singleton — loaded once at import time
settings = Settings()
