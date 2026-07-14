"""Central configuration, loaded from environment / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database / queue
    database_url: str = "postgresql+psycopg://attendance:changeme@db:5432/attendance"
    redis_url: str = "redis://redis:6379/0"

    # Auth
    jwt_secret: str = "insecure-dev-secret-change-me"
    jwt_expire_minutes: int = 720
    jwt_algorithm: str = "HS256"
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None

    # Face recognition
    face_match_threshold: float = 0.35
    face_det_score_min: float = 0.5
    face_provider: str = "CPUExecutionProvider"
    face_model_pack: str = "buffalo_l"

    # Storage / retention
    photo_dir: str = "/data/photos"
    photo_retention_minutes: int = 120
    retention_enabled: bool = True  # disable in tests

    # CORS
    cors_origins: str = "http://localhost:8000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
