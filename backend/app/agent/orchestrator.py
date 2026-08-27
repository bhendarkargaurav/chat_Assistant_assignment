"""Agent orchestration: route a turn to a skill, run it, persist the results.

    user turn -> TaskRouter -> Skill (RAG + LLM) -> answer + artifacts -> DB

Persistence is deliberately staged. The user message is committed before the
skill runs so a downstream LLM outage cannot lose the user's input, and artifact
persistence failures degrade to "content returned but not stored" instead of
throwing away an expensive generation.
"""

import logging
import time
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.agent.intents import Intent
from backend.app.agent.router import RouteDecision, TaskRouter
from backend.app.config import get_settings
from backend.app.db.models import Artifact, Message, MessageRole
from backend.app.db.models import Session as ChatSession
from backend.app.exceptions import NotFoundError, PersistenceError
from backend.app.observability.metrics import METRICS
from backend.app.schemas.source import SourceCitation
from backend.app.services.artifacts import ArtifactService
from backend.app.services.llm.base import LLMProvider
from backend.app.services.rag import RAGService
from backend.app.skills.base import ConversationTurn, SkillContext, SkillResult
from backend.app.skills.registry import get_skill

logger = logging.getLogger(__name__)


@dataclass
class AgentTurnResult:
    session_id: UUID
    answer: str
    route: RouteDecision
    skill: str
    sources: list[SourceCitation] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    provider: str = "unknown"


class AgentService:
    def __init__(
        self,
        db: Session,
        llm: LLMProvider,
        rag_service: RAGService | None = None,
        router: TaskRouter | None = None,
    ) -> None:
        self.db = db
        self.llm = llm
        self.settings = get_settings()
        self.rag_service = rag_service or RAGService(db)
        self.router = router or TaskRouter(llm=llm, settings=self.settings)
        self.artifacts = ArtifactService(db)

    def handle_turn(
        self,
        session_id: UUID,
        message: str,
        forced_intent: Intent | None = None,
        persist_user_message: bool = True,
    ) -> AgentTurnResult:
        session = self._get_session(session_id)
        history = self._load_history(session.id)

        user_message: Message | None = None
        if persist_user_message:
            user_message = self._persist_message(session, MessageRole.USER, message)

        route = (
            RouteDecision(
                intent=forced_intent,
                confidence=1.0,
                method="explicit",
                rationale="Intent supplied by the caller.",
            )
            if forced_intent is not None
            else self.router.route(message, _render_history(history))
        )

        skill = get_skill(route.intent)
        context = SkillContext(
            message=message,
            session_id=session.id,
            history=history,
            rag=self.rag_service,
            llm=self.llm,
            settings=self.settings,
            params=dict(route.params),
        )

        started = time.perf_counter()
        try:
            result: SkillResult = skill.run(context)
        except Exception:
            METRICS.increment("skill_failures_total", skill=skill.name)
            logger.exception(
                "Skill %s failed for session %s", skill.name, session.id
            )
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        METRICS.observe("skill_run", elapsed_ms, skill=skill.name)

        warnings = list(result.warnings)
        assistant_message = self._persist_message(
            session, MessageRole.ASSISTANT, result.answer, set_title_from=message
        )

        stored_artifacts: list[Artifact] = []
        for draft in result.artifacts:
            try:
                stored_artifacts.append(
                    self.artifacts.create_from_draft(
                        draft,
                        session_id=session.id,
                        message_id=assistant_message.id,
                        skill=skill.name,
                    )
                )
            except Exception as exc:
                # The generation itself succeeded; surface the content and warn.
                logger.exception("Artifact persistence failed for session %s", session.id)
                warnings.append(f"artifact_not_persisted: {exc}")

        logger.info(
            "Agent turn completed",
            extra={
                "session_id": str(session.id),
                "intent": route.intent.value,
                "skill": skill.name,
                "duration_ms": round(elapsed_ms, 2),
                "source_count": len(result.sources),
                "artifact_count": len(stored_artifacts),
                "warning_count": len(warnings),
            },
        )
        METRICS.increment("agent_turns_total", intent=route.intent.value)

        return AgentTurnResult(
            session_id=session.id,
            answer=result.answer,
            route=route,
            skill=skill.name,
            sources=result.sources,
            artifacts=stored_artifacts,
            metadata={
                **result.metadata,
                "user_message_id": str(user_message.id) if user_message else None,
                "assistant_message_id": str(assistant_message.id),
                "duration_ms": round(elapsed_ms, 2),
            },
            warnings=warnings,
            provider=self.llm.provider_name,
        )

    # -- internals ------------------------------------------------------

    def _get_session(self, session_id: UUID) -> ChatSession:
        session = self.db.get(ChatSession, session_id)
        if not session:
            raise NotFoundError(f"Session {session_id} not found")
        return session

    def _load_history(self, session_id: UUID) -> list[ConversationTurn]:
        rows = self.db.scalars(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(self.settings.conversation_history_limit)
        ).all()
        return [ConversationTurn(role=row.role, content=row.content) for row in reversed(rows)]

    def _persist_message(
        self,
        session: ChatSession,
        role: MessageRole,
        content: str,
        set_title_from: str | None = None,
    ) -> Message:
        message = Message(session_id=session.id, role=role.value, content=content)
        self.db.add(message)
        if set_title_from and not session.title:
            session.title = set_title_from[:80]
        try:
            self.db.commit()
            self.db.refresh(message)
        except SQLAlchemyError as exc:
            self.db.rollback()
            METRICS.increment("message_persistence_failures_total")
            logger.exception("Failed to persist %s message", role.value)
            raise PersistenceError(f"Could not persist {role.value} message: {exc}") from exc
        return message


def _render_history(history: list[ConversationTurn]) -> str:
    return "\n".join(f"{turn.role}: {turn.content[:500]}" for turn in history[-6:])
