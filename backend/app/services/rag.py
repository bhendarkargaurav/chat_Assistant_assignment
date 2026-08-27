import logging

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from backend.app.config import get_settings
from backend.app.db.models import Chunk, Document
from backend.app.exceptions import RetrievalError
from backend.app.schemas.source import SourceCitation
from backend.app.services.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class RAGService:
    def __init__(
        self,
        db: Session,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.db = db
        self.embedding_service = embedding_service or EmbeddingService()
        self.settings = get_settings()

    def retrieve(self, query: str, top_k: int | None = None) -> list[SourceCitation]:
        limit = top_k or self.settings.rag_top_k
        query_embedding = self.embedding_service.embed_text(query)

        distance_expr = Chunk.embedding.cosine_distance(query_embedding).label("distance")
        stmt = (
            select(Chunk, Document, distance_expr)
            .join(Document, Chunk.document_id == Document.id)
            .order_by(distance_expr)
            .limit(limit)
        )
        try:
            rows = self.db.execute(stmt).all()
        except SQLAlchemyError as exc:
            self.db.rollback()
            logger.exception("Vector search failed")
            raise RetrievalError(f"Vector search failed: {exc}") from exc

        citations: list[SourceCitation] = []
        for chunk, document, distance in rows:
            score = max(0.0, 1.0 - float(distance))
            excerpt = chunk.content[:300] + ("..." if len(chunk.content) > 300 else "")
            citations.append(
                SourceCitation(
                    document_id=document.id,
                    document_title=document.title,
                    chunk_id=chunk.id,
                    chunk_index=chunk.chunk_index,
                    excerpt=excerpt,
                    score=round(score, 4),
                )
            )

        logger.info("Retrieved %s chunks for query", len(citations))
        return citations

    def get_chunk_contents(self, chunk_ids: list) -> list[str]:
        if not chunk_ids:
            return []
        stmt = (
            select(Chunk)
            .options(joinedload(Chunk.document))
            .where(Chunk.id.in_(chunk_ids))
        )
        chunks = self.db.scalars(stmt).all()
        return [
            f"[Source: {chunk.document.title} (#{chunk.chunk_index})]\n{chunk.content}"
            for chunk in chunks
        ]
