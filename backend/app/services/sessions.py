from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import Session as ChatSession
from backend.app.exceptions import NotFoundError
from backend.app.schemas.session import SessionCreate, SessionDetailResponse, SessionResponse


class SessionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_session(self, payload: SessionCreate) -> SessionResponse:
        session = ChatSession(title=payload.title)
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return SessionResponse.model_validate(session)

    def get_session(self, session_id: UUID) -> SessionDetailResponse:
        session = self.db.get(ChatSession, session_id)
        if not session:
            raise NotFoundError(f"Session {session_id} not found")
        return SessionDetailResponse.model_validate(session)

    def list_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SessionResponse]:
        sessions = self.db.scalars(
            select(ChatSession)
            .order_by(ChatSession.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return [SessionResponse.model_validate(s) for s in sessions]
