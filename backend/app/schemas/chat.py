from uuid import UUID

from pydantic import BaseModel, Field


class SourceCitation(BaseModel):
    document_id: UUID
    document_title: str
    chunk_id: UUID
    chunk_index: int
    excerpt: str
    score: float


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)


class ChatResponse(BaseModel):
    session_id: UUID
    answer: str
    sources: list[SourceCitation] = Field(default_factory=list)
    provider: str
