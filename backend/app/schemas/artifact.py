from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.db.models import Artifact, ArtifactKind
from backend.app.schemas.source import SourceCitation
from backend.app.services.artifacts import ArtifactService


class ArtifactSummary(BaseModel):
    id: UUID
    session_id: UUID | None
    kind: ArtifactKind
    title: str
    skill: str
    word_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ArtifactResponse(ArtifactSummary):
    content: str
    sources: list[SourceCitation] = Field(default_factory=list)
    artifact_metadata: dict = Field(default_factory=dict)
    updated_at: datetime


class ArtifactGenerateRequest(BaseModel):
    instruction: str = Field(..., min_length=1, max_length=8000)
    kind: ArtifactKind = ArtifactKind.MARKDOWN


def to_summary(artifact: Artifact) -> ArtifactSummary:
    return ArtifactSummary.model_validate(artifact)


def to_response(artifact: Artifact) -> ArtifactResponse:
    return ArtifactResponse(
        id=artifact.id,
        session_id=artifact.session_id,
        kind=ArtifactKind(artifact.kind),
        title=artifact.title,
        skill=artifact.skill,
        word_count=artifact.word_count,
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
        content=artifact.content,
        sources=[
            SourceCitation.model_validate(source)
            for source in ArtifactService.parse_sources(artifact)
        ],
        artifact_metadata=ArtifactService.parse_metadata(artifact),
    )
