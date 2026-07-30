"""Application settings loaded from environment variables or a local .env file."""
from functools import lru_cache

from pydantic import EmailStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://attendance:changeme@localhost:5432/attendance"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "development-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 15
    jwt_refresh_token_days: int = 30
    auth_cookie_secure: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    bootstrap_admin_email: EmailStr | None = None
    bootstrap_admin_password: str | None = Field(default=None, min_length=8, max_length=128)
    profile_photo_dir: str = "data/profile_photos"
    face_model_pack: str = "buffalo_l"
    face_provider: str = "CPUExecutionProvider"
    face_detection_score_min: float = 0.5
    face_match_threshold: float = 0.35
    max_profile_photo_bytes: int = 10 * 1024 * 1024
    bulk_photo_root: str = "data/bulk_photos"
    session_photo_dir: str = "data/session_photos"
    session_photo_retention_days: int = 7

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
