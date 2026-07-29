from fastapi import APIRouter
import httpx

from app.core.config import settings


router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health():
    return {"status": "healthy", "application": "ClauseGuard RAG AI"}


@router.get("/capabilities")
def capabilities():
    ollama_available = False
    model_available = False
    if settings.ollama_enabled:
        try:
            response = httpx.get(
                f"{settings.ollama_url.rstrip('/')}/api/tags",
                timeout=1.5,
            )
            response.raise_for_status()
            ollama_available = True
            model_available = any(
                item.get("name") == settings.ollama_model
                for item in response.json().get("models", [])
            )
        except (httpx.HTTPError, TypeError, ValueError):
            pass
    return {
        "ollama": {
            "enabled": settings.ollama_enabled,
            "available": ollama_available,
            "model": settings.ollama_model,
            "model_available": model_available,
        },
        "qdrant": {
            "enabled": settings.qdrant_enabled,
            "mode": "vector_and_lexical" if settings.qdrant_enabled else "lexical_fallback",
        },
        "ocr": {
            "enabled": settings.ocr_enabled,
            "language": settings.ocr_language,
        },
        "risk_second_pass": settings.llm_risk_second_pass_enabled,
        "finding_verification": settings.llm_finding_verification_enabled,
        "pipeline_version": settings.pipeline_version,
        "score_status": "explainable_index_not_calibrated_probability",
    }
