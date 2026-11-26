from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Konfigurasi aplikasi yang dimuat dari environment / file .env."""

    model_config = SettingsConfigDict(
        env_file=str(ROOT_ENV) if ROOT_ENV.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATA_PROVIDER: str = "mock"
    FOOTBALL_DATA_API_KEY: str = ""
    API_FOOTBALL_KEY: str = ""
    FOOTYSTATS_API_KEY: str = ""

    DATABASE_URL: str = "sqlite:///./football_analytics.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET: str = "dev_secret_change_me"
    JWT_ALGORITHM: str = "HS256"
    GOOGLE_CLIENT_ID: str = ""
    ENABLE_EMBEDDED_WORKER: bool = True

    # Google Apps Script Spreadsheet Sync (opsional)
    GSHEET_WEBAPP_URL: str = ""
    GSHEET_SYNC_SECRET: str = ""

    NEXT_PUBLIC_API_URL: str = "http://localhost:8000"


settings = Settings()
