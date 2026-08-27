from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.chat import ChatRequest, ChatResponse
from backend.app.services.chat import ChatService

router = APIRouter(prefix="/sessions", tags=["chat"])


@router.post("/{session_id}/chat", response_model=ChatResponse)
def chat_in_session(
    session_id: UUID,
    payload: ChatRequest,
    db: Session = Depends(get_db),
) -> ChatResponse:
    return ChatService(db).chat(session_id, payload)
