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
    data_dir: str = "data"
    face_model_pack: str = "buffalo_l"
    face_provider: str = "CPUExecutionProvider"
    face_detection_score_min: float = 0.5
    face_match_threshold: float = 0.35
    max_profile_photo_bytes: int = 10 * 1024 * 1024
    max_bulk_zip_bytes: int = 100 * 1024 * 1024
    max_bulk_zip_files: int = 5000
    max_spreadsheet_bytes: int = 10 * 1024 * 1024
    max_session_photos: int = 20
    session_photo_dir: str = "data/session_photos"
    session_photo_retention_days: int = 7
    storage_backend: str = "local"
    storage_bucket: str | None = None
    storage_region: str | None = None
    storage_endpoint_url: str | None = None
    storage_access_key_id: str | None = None
    storage_secret_access_key: str | None = None
    email_enabled: bool = True
    email_backend: str = "smtp"
    email_from: str = "noreply@classlens.local"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = False
    ses_region: str | None = None
    ses_configuration_set: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
