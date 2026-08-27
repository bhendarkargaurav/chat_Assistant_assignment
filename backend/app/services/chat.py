import logging
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.agent.intents import Intent
from backend.app.agent.orchestrator import AgentService, AgentTurnResult
from backend.app.schemas.artifact import to_summary
from backend.app.schemas.chat import ChatRequest, ChatResponse, RoutingInfo
from backend.app.services.llm.factory import get_llm_provider

logger = logging.getLogger(__name__)


class ChatService:
    """Thin HTTP-facing wrapper around the agent orchestrator."""

    def __init__(self, db: Session, agent: AgentService | None = None) -> None:
        self.db = db
        self.agent = agent or AgentService(db, llm=get_llm_provider())

    def chat(
        self,
        session_id: UUID,
        request: ChatRequest,
        forced_intent: Intent | None = None,
    ) -> ChatResponse:
        result = self.agent.handle_turn(
            session_id, request.message, forced_intent=forced_intent
        )
        return to_chat_response(result)


def to_chat_response(result: AgentTurnResult) -> ChatResponse:
    return ChatResponse(
        session_id=result.session_id,
        answer=result.answer,
        sources=result.sources,
        provider=result.provider,
        skill=result.skill,
        routing=RoutingInfo(
            intent=result.route.intent.value,
            confidence=result.route.confidence,
            method=result.route.method,
            rationale=result.route.rationale,
            scores=result.route.scores,
        ),
        artifacts=[to_summary(artifact) for artifact in result.artifacts],
        warnings=result.warnings,
        metadata=result.metadata,
    )
