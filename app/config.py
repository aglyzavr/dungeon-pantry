from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_port: int = 8080
    app_env: str = "development"

    # Database
    postgres_host: str
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: str

    # Sessions
    session_secret_key: str
    session_duration_days: int = 30

    @property
    def database_url(self) -> str:
        """Async PostgreSQL connection URL for SQLAlchemy."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    # Pydantic-settings: read from .env file automatically
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    """
    Cached singleton — settings are loaded once at startup.
    Using lru_cache means the .env file is only parsed once,
    and the same Settings instance is reused everywhere via FastAPI Depends().
    """
    return Settings()
