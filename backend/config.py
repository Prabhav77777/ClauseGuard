"""Application configuration loaded from environment variables.

All settings are loaded via pydantic-settings from .env or environment variables.
No secrets are ever hardcoded. The API key is validated at startup when needed,
not during module import, to allow tests to run without a key.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """ClauseGuard application settings.
    
    Loaded from environment variables or .env file.
    See .env.example for documentation of each setting.
    """
    # API key is optional at import time to allow tests to run without it.
    # It is validated at runtime before any LLM call.
    ANTHROPIC_API_KEY: str = ""
    
    # Document limits
    MAX_FILE_SIZE_MB: int = 10
    MAX_PAGES: int = 50
    MAX_CHARACTERS: int = 500000
    
    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 10
    RATE_LIMIT_PERIOD: str = "minute"
    
    # Session management
    SESSION_TTL_SECONDS: int = 3600
    
    # Claude model selection
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
    
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
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Module-level singleton — loaded once at import time
settings = Settings()
