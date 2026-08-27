import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from backend.app.api.routes import chat, documents, health, sessions
from backend.app.config import get_settings
from backend.app.db.session import init_db
from backend.app.exceptions import AppError
from backend.app.logging_config import setup_logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Lenny Growth Assistant — grounded Q&A over podcast transcripts",
    )

    @app.on_event("startup")
    def on_startup() -> None:
        init_db()
        logger.info("Application started env=%s provider=%s", settings.app_env, settings.llm_provider)

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        logger.error("Application error: %s", exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "error_type": exc.__class__.__name__},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors(), "error_type": "ValidationError"},
        )

    @app.exception_handler(ValidationError)
    async def pydantic_validation_handler(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors(), "error_type": "ValidationError"},
        )

    app.include_router(health.router)
    app.include_router(sessions.router)
    app.include_router(chat.router)
    app.include_router(documents.router)

    return app


app = create_app()
