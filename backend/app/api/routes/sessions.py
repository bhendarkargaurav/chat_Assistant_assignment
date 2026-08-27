from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.session import SessionCreate, SessionDetailResponse, SessionResponse
from backend.app.services.sessions import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=201)
def create_session(
    payload: SessionCreate,
    db: Session = Depends(get_db),
) -> SessionResponse:
    return SessionService(db).create_session(payload)


@router.get("", response_model=list[SessionResponse])
def list_sessions(db: Session = Depends(get_db)) -> list[SessionResponse]:
    return SessionService(db).list_sessions()


@router.get("/{session_id}", response_model=SessionDetailResponse)
def get_session(
    session_id: UUID,
    db: Session = Depends(get_db),
) -> SessionDetailResponse:
    return SessionService(db).get_session(session_id)
