"""Application settings, loaded from environment variables / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "URL Shortener & Analytics"
    PROJECT_DESCRIPTION: str = (
        "A URL shortener with JWT auth, Redis caching and click analytics."
    )
    API_PREFIX: str = "/api"

    # --- Infrastructure ---
    DATABASE_URL: str = "sqlite:///./urlshortener.db"
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None
    # When true, Celery runs tasks inline instead of sending them to a worker.
    CELERY_TASK_ALWAYS_EAGER: bool = False

    # --- Auth ---
    JWT_SECRET_KEY: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # --- Shortening ---
    BASE_URL: str = "http://localhost:8000"
    SHORT_CODE_LENGTH: int = 6
    MIN_ALIAS_LENGTH: int = 3
    MAX_ALIAS_LENGTH: int = 32
    CACHE_TTL_SECONDS: int = 3600

    # --- Misc ---
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def broker_url(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @property
    def result_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()