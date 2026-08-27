import logging

from backend.app.skills.base import (
    Skill,
    SkillContext,
    SkillResult,
    format_context_blocks,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Lenny Growth Assistant, an expert on product and growth
topics grounded in Lenny Rachitsky's podcast transcripts.

Rules:
- Answer using ONLY the provided transcript excerpts and the conversation history.
- If the excerpts do not contain enough information, say so plainly instead of guessing.
- Cite sources inline using the [Source: title (#chunk_index)] format.
- Be concise, practical and specific."""

USER_PROMPT = """Conversation history:
{history}

Retrieved transcript excerpts:
{context}

User question:
{question}

Provide a grounded answer with inline source citations."""


class GroundedQASkill(Skill):
    name = "grounded_qa"
    description = (
        "Answer a question about product growth using retrieved podcast transcript "
        "excerpts, with inline source citations."
    )

    def run(self, context: SkillContext) -> SkillResult:
        warnings: list[str] = []
        sources = self.retrieve(context, context.message, warnings=warnings)

        answer = self.generate(
            context,
            SYSTEM_PROMPT,
            USER_PROMPT.format(
                history=context.history_text(),
                context=format_context_blocks(sources),
                question=context.message,
            ),
        )

        logger.info(
            "grounded_qa produced an answer",
            extra={"skill": self.name, "source_count": len(sources)},
        )

        return SkillResult(
            answer=answer,
            sources=sources,
            metadata={"grounded": bool(sources)},
            warnings=warnings,
        )
