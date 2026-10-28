from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    JWT_SECRET: str = "dev-only-secret-change-me-0123456789abcdef"
    JWT_EXPIRE_MINUTES: int = 120
    DATABASE_URL: str = f"sqlite:///{(ROOT / 'data' / 'hospital.db').as_posix()}"

    # MOCK_AI=true returns canned /chat responses (UI development / demo fallback).
    MOCK_AI: bool = False

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    RATE_LIMIT_ENABLED: bool = True
    CHAT_RATE: str = "20/minute"
    LOGIN_RATE: str = "5/minute"

    PENDING_ACTION_MINUTES: int = 10
    CHANGE_WINDOW_HOURS: int = 24

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
