"""Application settings, loaded from environment variables (or a .env file).

Every setting has a sensible default for local development, so the app runs
with zero configuration. Override anything in production via env vars, e.g.
DATABASE_URL=postgresql+psycopg://user:pass@db:5432/partify
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- General ---
    app_name: str = "Partify"
    environment: str = "development"
    secret_key: str = "dev-secret-change-me-in-production-please-32+chars"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    # Comma separated list of origins allowed to call the API from a browser.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    currency: str = "JOD"

    # --- Database ---
    database_url: str = "postgresql+psycopg://partify:partify@localhost:5432/partify"

    # --- Uploads (marketplace photos, avatars) ---
    upload_dir: str = "uploads"
    max_upload_mb: int = 5
    max_images_per_listing: int = 6

    # --- Seeding (python -m app.cli init) ---
    admin_email: str | None = None
    admin_password: str | None = None
    admin_username: str = "admin"
    # Demo accounts + marketplace ads for presentations. They share a public password: keep OFF in production.
    seed_demo_users: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
