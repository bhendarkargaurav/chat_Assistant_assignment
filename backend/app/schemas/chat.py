from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.agent.intents import Intent
from backend.app.schemas.artifact import ArtifactSummary
from backend.app.schemas.source import SourceCitation

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "RoutingInfo",
    "SourceCitation",
]


class RoutingInfo(BaseModel):
    intent: str
    confidence: float
    method: str
    rationale: str
    scores: dict[str, float] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    intent: Intent | None = Field(
        default=None,
        description="Bypass the router and force a specific skill.",
    )


class ChatResponse(BaseModel):
    session_id: UUID
    answer: str
    sources: list[SourceCitation] = Field(default_factory=list)
    provider: str
    skill: str = "grounded_qa"
    routing: RoutingInfo | None = None
    artifacts: list[ArtifactSummary] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
