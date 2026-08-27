import json
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import Chunk, Document
from backend.app.exceptions import ValidationAppError
from backend.app.schemas.document import DocumentIngestRequest, DocumentResponse
from backend.app.services.chunking import chunk_text
from backend.app.services.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


def _content_hash(content: str) -> str:
    import hashlib

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class IngestionService:
    def __init__(self, db: Session, embedding_service: EmbeddingService | None = None) -> None:
        self.db = db
        self.embedding_service = embedding_service or EmbeddingService()

    def ingest_document(self, request: DocumentIngestRequest) -> DocumentResponse:
        content_hash = _content_hash(request.content)
        existing = self.db.scalar(
            select(Document).where(Document.content_hash == content_hash)
        )
        if existing:
            chunk_count = len(existing.chunks)
            return DocumentResponse(
                id=existing.id,
                title=existing.title,
                source=existing.source,
                content_hash=existing.content_hash,
                chunk_count=chunk_count,
                created_at=existing.created_at,
            )

        document = Document(
            title=request.title,
            source=request.source,
            content_hash=content_hash,
            metadata_json=json.dumps(request.metadata) if request.metadata else None,
        )
        self.db.add(document)
        self.db.flush()

        chunks = chunk_text(request.content)
        if not chunks:
            raise ValidationAppError("Document content produced no chunks")

        embeddings = self.embedding_service.embed_texts(chunks)
        for index, (chunk_content, embedding) in enumerate(zip(chunks, embeddings)):
            self.db.add(
                Chunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=chunk_content,
                    embedding=embedding,
                    token_count=len(chunk_content.split()),
                )
            )

        self.db.commit()
        self.db.refresh(document)
        logger.info("Ingested document %s with %s chunks", document.id, len(chunks))

        return DocumentResponse(
            id=document.id,
            title=document.title,
            source=document.source,
            content_hash=document.content_hash,
            chunk_count=len(chunks),
            created_at=document.created_at,
        )

    def ingest_directory(self, directory: Path) -> tuple[list[DocumentResponse], list[str]]:
        ingested: list[DocumentResponse] = []
        skipped: list[str] = []

        if not directory.exists():
            raise ValidationAppError(f"Directory not found: {directory}")

        for path in sorted(directory.glob("*.txt")):
            content = path.read_text(encoding="utf-8")
            title = path.stem.replace("_", " ")
            try:
                result = self.ingest_document(
                    DocumentIngestRequest(
                        title=title,
                        source=str(path.name),
                        content=content,
                        metadata={"filename": path.name},
                    )
                )
                ingested.append(result)
            except Exception as exc:
                logger.exception("Failed to ingest %s", path)
                skipped.append(f"{path.name}: {exc}")

        return ingested, skipped

    def get_document(self, document_id: UUID) -> Document | None:
        return self.db.get(Document, document_id)
