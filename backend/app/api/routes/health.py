import logging

from fastapi import APIRouter
from sqlalchemy import text

from backend.app.config import get_settings
from backend.app.db.session import get_engine
from backend.app.services.embeddings import EmbeddingService
from backend.app.services.llm.factory import get_llm_provider

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": get_settings().app_name}


@router.get("/ready")
def ready() -> dict:
    settings = get_settings()
    checks: dict[str, str] = {}

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        logger.warning("Database readiness check failed: %s", exc)
        checks["database"] = "error"

    llm = get_llm_provider()
    checks["llm"] = "ok" if llm.health_check() else "degraded"

    embedding_service = EmbeddingService()
    checks["embeddings"] = "ok" if embedding_service.health_check() else "degraded"

    overall = "ok" if checks["database"] == "ok" else "degraded"
    return {
        "status": overall,
        "provider": settings.llm_provider,
        "checks": checks,
    }
