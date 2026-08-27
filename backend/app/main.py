import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from backend.app.api.routes import artifacts, chat, documents, health, sessions
from backend.app.config import get_settings
from backend.app.db.session import init_db
from backend.app.exceptions import AppError
from backend.app.logging_config import setup_logging
from backend.app.observability.context import get_request_id
from backend.app.observability.metrics import METRICS
from backend.app.observability.middleware import RequestContextMiddleware

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            init_db()
        except Exception:
            # Fail loudly in the logs but let the process serve /health so an
            # orchestrator can report the pod as unready instead of crash-looping.
            logger.exception("Database initialization failed at startup")
        logger.info(
            "Application started",
            extra={"env": settings.app_env, "provider": settings.llm_provider},
        )
        yield

    app = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        description=(
            "Lenny Growth Assistant — agent-routed grounded Q&A, Ship 30 for 30 essays "
            "and markdown/HTML artifacts over podcast transcripts"
        ),
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        logger.error(
            "Application error: %s",
            exc.message,
            extra={"error_type": exc.__class__.__name__, "status_code": exc.status_code},
        )
        METRICS.increment("app_errors_total", error_type=exc.__class__.__name__)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.message,
                "error_type": exc.__class__.__name__,
                "request_id": get_request_id(),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": exc.errors(),
                "error_type": "ValidationError",
                "request_id": get_request_id(),
            },
        )

    @app.exception_handler(ValidationError)
    async def pydantic_validation_handler(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": exc.errors(),
                "error_type": "ValidationError",
                "request_id": get_request_id(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", exc)
        METRICS.increment("app_errors_total", error_type="UnhandledError")
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "error_type": "UnhandledError",
                "request_id": get_request_id(),
            },
        )

    app.include_router(health.router)
    app.include_router(sessions.router)
    app.include_router(chat.router)
    app.include_router(documents.router)
    app.include_router(artifacts.router)
    app.include_router(artifacts.session_router)

    return app


app = create_app()
