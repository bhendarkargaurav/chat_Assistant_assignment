from uuid import UUID

from pydantic import BaseModel


class SourceCitation(BaseModel):
    """A transcript chunk used to ground generated content."""

    document_id: UUID
    document_title: str
    chunk_id: UUID
    chunk_index: int
    excerpt: str
    score: float
