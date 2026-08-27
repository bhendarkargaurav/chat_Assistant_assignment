from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.document import (
    DocumentIngestRequest,
    DocumentResponse,
    IngestDirectoryResponse,
)
from backend.app.services.ingestion import IngestionService

router = APIRouter(prefix="/documents", tags=["documents"])

DEFAULT_TRANSCRIPT_DIR = Path(__file__).resolve().parents[4] / "data" / "transcripts"


@router.post("/ingest", response_model=DocumentResponse, status_code=201)
def ingest_document(
    payload: DocumentIngestRequest,
    db: Session = Depends(get_db),
) -> DocumentResponse:
    return IngestionService(db).ingest_document(payload)


@router.post("/ingest-directory", response_model=IngestDirectoryResponse)
def ingest_directory(
    db: Session = Depends(get_db),
) -> IngestDirectoryResponse:
    service = IngestionService(db)
    ingested, skipped = service.ingest_directory(DEFAULT_TRANSCRIPT_DIR)
    return IngestDirectoryResponse(ingested=ingested, skipped=skipped)
