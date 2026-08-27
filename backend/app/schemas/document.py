from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentIngestRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    source: str = Field(..., min_length=1, max_length=512)
    content: str = Field(..., min_length=1)
    metadata: dict | None = None


class DocumentResponse(BaseModel):
    id: UUID
    title: str
    source: str
    content_hash: str
    chunk_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class IngestDirectoryResponse(BaseModel):
    ingested: list[DocumentResponse]
    skipped: list[str] = Field(default_factory=list)
