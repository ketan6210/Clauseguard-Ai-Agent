from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "ClauseGuard RAG AI"
    pipeline_version: str = "2026.07-advanced-score-v2"
    environment: str = "development"
    database_url: str = f"sqlite:///{BACKEND_DIR / 'clauseguard.db'}"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "clauseguard_policies"
    qdrant_clause_collection: str = "clauseguard_contract_clauses"
    qdrant_enabled: bool = True
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    contract_retrieval_min_score: float = 0.18
    policy_retrieval_min_score: float = 0.15
    ocr_enabled: bool = True
    ocr_language: str = "eng"
    ocr_dpi: int = 200
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    ollama_enabled: bool = False
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"
    ollama_timeout_seconds: float = 120
    llm_risk_second_pass_enabled: bool = False
    llm_risk_min_confidence: float = 0.7
    llm_finding_verification_enabled: bool = True
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
