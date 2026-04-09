from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from urllib.parse import quote_plus


class Settings(BaseSettings):
    # App
    app_port: int = 8080
    app_env: str = "development"

    # Database — either provide DATABASE_URL (Railway style) or individual vars
    database_url_override: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DATABASE_URL", "database_url_override"),
    )

    postgres_host: str | None = None
    postgres_port: int = 5432
    postgres_db: str | None = None
    postgres_user: str | None = None
    postgres_password: str | None = None
    db_pool_size: int = 10
    db_max_overflow: int = 5

    # Sessions
    session_secret_key: str
    session_duration_days: int = 30

    # DM seed user — optional, only used on first startup
    dm_seed_username: str = "dm"
    dm_seed_password: str | None = None

    @property
    def database_url(self) -> str:
        # Prefer DATABASE_URL if provided (e.g. Railway auto-injects this)
        if self.database_url_override:
            url = self.database_url_override
            # Railway provides a postgres:// or postgresql:// URL; upgrade to asyncpg driver
            if url.startswith("postgres://"):
                url = "postgresql+asyncpg://" + url[len("postgres://"):]
            elif url.startswith("postgresql://"):
                url = "postgresql+asyncpg://" + url[len("postgresql://"):]
            return url

        # Fall back to individual POSTGRES_* variables
        if not all([self.postgres_host, self.postgres_db, self.postgres_user, self.postgres_password]):
            raise ValueError(
                "Database configuration is missing. "
                "Set DATABASE_URL or all of POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD."
            )
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
