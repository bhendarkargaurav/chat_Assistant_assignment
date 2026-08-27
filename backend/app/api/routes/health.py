import logging

from fastapi import APIRouter
from sqlalchemy import text

from backend.app.config import get_settings
from backend.app.db.session import get_engine
from backend.app.observability.metrics import METRICS
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

    try:
        checks["llm"] = "ok" if get_llm_provider().health_check() else "degraded"
    except Exception as exc:
        logger.warning("LLM readiness check failed: %s", exc)
        checks["llm"] = "error"

    try:
        checks["embeddings"] = (
            "ok" if EmbeddingService().health_check() else "degraded"
        )
    except Exception as exc:
        logger.warning("Embedding readiness check failed: %s", exc)
        checks["embeddings"] = "error"

    overall = "ok" if checks["database"] == "ok" else "degraded"
    return {
        "status": overall,
        "provider": settings.llm_provider,
        "checks": checks,
    }


@router.get("/metrics")
def metrics() -> dict:
    """In-process counters and latency summaries (see observability.metrics)."""
    return METRICS.snapshot()
