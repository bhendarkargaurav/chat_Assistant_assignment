"""Skill contract shared by every agent capability.

A skill receives a :class:`SkillContext` (user message, conversation history and
handles to retrieval + the LLM) and returns a :class:`SkillResult` containing
the chat answer, the grounding sources and any artifacts to persist. The agent
orchestrator owns persistence, so skills stay side-effect free and easy to test.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from uuid import UUID

from backend.app.config import Settings
from backend.app.db.models import ArtifactKind
from backend.app.exceptions import LLMError
from backend.app.observability.metrics import METRICS
from backend.app.schemas.source import SourceCitation
from backend.app.services.llm.base import LLMProvider
from backend.app.services.rag import RAGService
from backend.app.services.resilience import retry_call

logger = logging.getLogger(__name__)


@dataclass
class ConversationTurn:
    role: str
    content: str


@dataclass
class SkillContext:
    message: str
    session_id: UUID | None
    history: list[ConversationTurn]
    rag: RAGService
    llm: LLMProvider
    settings: Settings
    params: dict = field(default_factory=dict)

    def history_text(self, limit: int | None = None) -> str:
        turns = self.history[-(limit or self.settings.conversation_history_limit) :]
        if not turns:
            return "(no prior conversation)"
        return "\n".join(f"{turn.role}: {turn.content}" for turn in turns)

    def last_assistant_message(self) -> str | None:
        for turn in reversed(self.history):
            if turn.role == "assistant":
                return turn.content
        return None


@dataclass
class ArtifactDraft:
    kind: ArtifactKind
    title: str
    content: str
    sources: list[SourceCitation] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def word_count(self) -> int:
        return count_words(self.content)


@dataclass
class SkillResult:
    answer: str
    sources: list[SourceCitation] = field(default_factory=list)
    artifacts: list[ArtifactDraft] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class Skill(ABC):
    name: str
    description: str

    @abstractmethod
    def run(self, context: SkillContext) -> SkillResult:
        raise NotImplementedError

    # -- shared helpers -------------------------------------------------

    def retrieve(
        self,
        context: SkillContext,
        query: str,
        top_k: int | None = None,
        warnings: list[str] | None = None,
    ) -> list[SourceCitation]:
        """Retrieve grounding chunks, degrading to an ungrounded answer on failure.

        A retrieval outage should not take the whole assistant down: we log,
        record a metric, warn the caller and let the skill answer without
        context (the prompts instruct the model to admit missing grounding).
        """
        try:
            sources = context.rag.retrieve(query, top_k=top_k)
        except Exception as exc:
            logger.exception("Retrieval failed for skill %s", self.name)
            METRICS.increment("retrieval_failures_total", skill=self.name)
            if warnings is not None:
                warnings.append(f"retrieval_unavailable: {exc}")
            return []

        METRICS.increment("retrieval_calls_total", skill=self.name)
        if not sources and warnings is not None:
            warnings.append("no_matching_sources")
        return sources

    def generate(self, context: SkillContext, system_prompt: str, user_prompt: str) -> str:
        """Call the LLM with retries; raises :class:`LLMError` when exhausted."""
        try:
            output = retry_call(
                f"llm.generate[{self.name}]",
                lambda: context.llm.generate(system_prompt, user_prompt),
                attempts=context.settings.llm_max_attempts,
            )
        except Exception as exc:
            METRICS.increment("llm_failures_total", skill=self.name)
            raise LLMError(f"LLM generation failed for skill {self.name}: {exc}") from exc

        METRICS.increment("llm_calls_total", skill=self.name)
        if not output or not output.strip():
            METRICS.increment("llm_empty_responses_total", skill=self.name)
            raise LLMError(f"LLM returned an empty response for skill {self.name}")
        return output.strip()


def strip_code_fence(text: str) -> str:
    """Remove a surrounding ```lang ... ``` fence that models like to add."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def count_words(text: str) -> int:
    return len([token for token in text.split() if token.strip()])


def format_context_blocks(sources: list[SourceCitation]) -> str:
    if not sources:
        return "No relevant transcript excerpts were retrieved."
    return "\n\n".join(
        f"[Source: {source.document_title} (#{source.chunk_index})]\n{source.excerpt}"
        for source in sources
    )
