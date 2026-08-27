import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import Message, MessageRole, Session as ChatSession
from backend.app.exceptions import NotFoundError
from backend.app.schemas.chat import ChatRequest, ChatResponse
from backend.app.services.llm.factory import get_llm_provider
from backend.app.services.rag import RAGService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Lenny Growth Assistant, an expert on product growth topics
based on Lenny Rachitsky's podcast transcripts.

Answer the user's question using ONLY the provided transcript excerpts.
If the excerpts do not contain enough information, say so clearly.
Cite sources inline using [Source: title (#chunk_index)] format.
Be concise, practical, and grounded in the source material."""


class ChatService:
    def __init__(self, db: Session, rag_service: RAGService | None = None) -> None:
        self.db = db
        self.rag_service = rag_service or RAGService(db)

    def _get_session(self, session_id: UUID) -> ChatSession:
        session = self.db.get(ChatSession, session_id)
        if not session:
            raise NotFoundError(f"Session {session_id} not found")
        return session

    def chat(self, session_id: UUID, request: ChatRequest) -> ChatResponse:
        session = self._get_session(session_id)
        llm = get_llm_provider()

        user_message = Message(
            session_id=session.id,
            role=MessageRole.USER.value,
            content=request.message,
        )
        self.db.add(user_message)
        self.db.flush()

        sources = self.rag_service.retrieve(request.message)
        context_blocks = []
        for source in sources:
            context_blocks.append(
                f"[Source: {source.document_title} (#{source.chunk_index})]\n"
                f"{source.excerpt}"
            )

        context_text = "\n\n".join(context_blocks) if context_blocks else "No relevant excerpts found."
        history = self.db.scalars(
            select(Message)
            .where(Message.session_id == session.id)
            .order_by(Message.created_at.desc())
            .limit(10)
        ).all()
        history_text = "\n".join(
            f"{msg.role}: {msg.content}" for msg in reversed(history[:-1])
        )

        user_prompt = f"""Conversation history:
{history_text or "(none)"}

Retrieved transcript excerpts:
{context_text}

User question:
{request.message}

Provide a grounded answer with inline source citations."""

        answer = llm.generate(SYSTEM_PROMPT, user_prompt)

        assistant_message = Message(
            session_id=session.id,
            role=MessageRole.ASSISTANT.value,
            content=answer,
        )
        self.db.add(assistant_message)

        if not session.title:
            session.title = request.message[:80]

        self.db.commit()

        logger.info(
            "Chat completed for session %s with %s sources via %s",
            session_id,
            len(sources),
            llm.provider_name,
        )

        return ChatResponse(
            session_id=session.id,
            answer=answer,
            sources=sources,
            provider=llm.provider_name,
        )
