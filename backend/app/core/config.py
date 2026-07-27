from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "ClauseGuard RAG AI"
    environment: str = "development"
    database_url: str = f"sqlite:///{BACKEND_DIR / 'clauseguard.db'}"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "clauseguard_policies"
    qdrant_enabled: bool = True
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    upload_dir: str = str(BACKEND_DIR / "uploads")
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
