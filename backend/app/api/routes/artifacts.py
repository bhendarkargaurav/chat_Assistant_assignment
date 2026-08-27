import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from backend.app.agent.intents import Intent
from backend.app.db.models import ArtifactKind
from backend.app.db.session import get_db
from backend.app.schemas.artifact import (
    ArtifactGenerateRequest,
    ArtifactResponse,
    ArtifactSummary,
    to_response,
    to_summary,
)
from backend.app.schemas.chat import ChatRequest, ChatResponse
from backend.app.services.artifacts import ArtifactService
from backend.app.services.chat import ChatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/artifacts", tags=["artifacts"])
session_router = APIRouter(prefix="/sessions", tags=["artifacts"])

_INTENT_BY_KIND = {
    ArtifactKind.MARKDOWN: Intent.ARTIFACT_MARKDOWN,
    ArtifactKind.HTML: Intent.ARTIFACT_HTML,
}

# Stored HTML is already sanitized; the CSP is the second layer that keeps a
# sanitizer regression from turning into script execution in a browser.
_HTML_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; img-src https: data:; "
        "font-src https:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


@router.get("", response_model=list[ArtifactSummary])
def list_artifacts(
    session_id: UUID | None = None,
    kind: ArtifactKind | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[ArtifactSummary]:
    artifacts = ArtifactService(db).list_artifacts(
        session_id=session_id, kind=kind, limit=limit, offset=offset
    )
    return [to_summary(artifact) for artifact in artifacts]


@router.get("/{artifact_id}", response_model=ArtifactResponse)
def get_artifact(artifact_id: UUID, db: Session = Depends(get_db)) -> ArtifactResponse:
    return to_response(ArtifactService(db).get(artifact_id))


@router.get("/{artifact_id}/raw", response_class=Response)
def get_artifact_raw(artifact_id: UUID, db: Session = Depends(get_db)) -> Response:
    """Serve artifact content with its native content type and hardened headers."""
    service = ArtifactService(db)
    artifact = service.get(artifact_id)
    content = service.ensure_renderable(artifact)

    if artifact.kind == ArtifactKind.HTML.value:
        return Response(
            content=content,
            media_type="text/html; charset=utf-8",
            headers=_HTML_SECURITY_HEADERS,
        )
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.delete("/{artifact_id}", status_code=204)
def delete_artifact(artifact_id: UUID, db: Session = Depends(get_db)) -> Response:
    ArtifactService(db).delete(artifact_id)
    return Response(status_code=204)


@session_router.get("/{session_id}/artifacts", response_model=list[ArtifactSummary])
def list_session_artifacts(
    session_id: UUID,
    kind: ArtifactKind | None = None,
    db: Session = Depends(get_db),
) -> list[ArtifactSummary]:
    artifacts = ArtifactService(db).list_artifacts(session_id=session_id, kind=kind, limit=200)
    return [to_summary(artifact) for artifact in artifacts]


@session_router.post("/{session_id}/artifacts", response_model=ChatResponse, status_code=201)
def generate_session_artifact(
    session_id: UUID,
    payload: ArtifactGenerateRequest,
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Generate an artifact of an explicit kind, skipping intent routing."""
    return ChatService(db).chat(
        session_id,
        ChatRequest(message=payload.instruction),
        forced_intent=_INTENT_BY_KIND[payload.kind],
    )
