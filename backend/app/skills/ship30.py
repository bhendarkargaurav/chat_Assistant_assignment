"""Ship 30 for 30 essay skill.

Ship 30 for 30 is a daily writing challenge built around "atomic essays": a
sharp hook, one big idea, concrete proof and an actionable takeaway. This skill
turns a topic into a ~1,250-word atomic essay that is grounded in the ingested
Lenny transcripts and carries explicit source attribution.
"""

import logging

from backend.app.db.models import ArtifactKind
from backend.app.schemas.source import SourceCitation
from backend.app.skills.base import (
    ArtifactDraft,
    Skill,
    SkillContext,
    SkillResult,
    count_words,
    format_context_blocks,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Ship 30 for 30 writing coach and ghostwriter for the Lenny
Growth Assistant. You write atomic essays: one big idea, argued clearly, in the
voice of a practitioner talking to other practitioners.

Structure every essay as:
1. A hook of 1-2 sentences that names the tension or the misconception.
2. A short framing section explaining why the idea matters right now.
3. Three body sections, each with a `##` heading, a claim, evidence drawn from the
   transcript excerpts, and a concrete example.
4. A "How to apply this" section with 3-5 numbered, specific actions.
5. A one-line closing takeaway the reader can quote.

Hard rules:
- Ground every factual claim in the supplied transcript excerpts and cite them
  inline as [Source: title (#chunk_index)].
- If the excerpts do not support a point, say what is uncertain rather than inventing
  data, names, numbers or quotes.
- Write in markdown, starting with a single `#` title. Do not add a sources section;
  it is appended automatically.
- Short paragraphs (1-3 sentences). No filler, no throat-clearing, no emoji."""

USER_PROMPT = """Conversation so far (use it to stay consistent with what was already discussed):
{history}

Transcript excerpts to ground the essay in:
{context}

Essay request:
{request}

Write a Ship 30 for 30 atomic essay of approximately {target} words (between {minimum}
and {maximum} words). Return only the markdown essay."""

EXPANSION_PROMPT = """The draft below is {actual} words but must be between {minimum} and
{maximum} words (target {target}).

Revise it to hit the target while keeping the Ship 30 for 30 structure, the existing
inline [Source: ...] citations and the grounding in these excerpts:
{context}

{instruction}

Draft:
---
{draft}
---

Return only the revised markdown essay."""


class Ship30Skill(Skill):
    name = "ship30_essay"
    description = (
        "Write a ~1,250-word Ship 30 for 30 atomic essay grounded in Lenny podcast "
        "transcripts, with inline citations and a sources section."
    )

    def run(self, context: SkillContext) -> SkillResult:
        warnings: list[str] = []
        settings = context.settings
        target = settings.essay_target_words
        minimum = int(target * (1 - settings.essay_word_tolerance))
        maximum = int(target * (1 + settings.essay_word_tolerance))

        topic = context.params.get("topic") or context.message
        sources = self.retrieve(
            context,
            topic,
            top_k=settings.rag_essay_top_k,
            warnings=warnings,
        )
        context_blocks = format_context_blocks(sources)

        essay = self.generate(
            context,
            SYSTEM_PROMPT,
            USER_PROMPT.format(
                history=context.history_text(),
                context=context_blocks,
                request=context.message,
                target=target,
                minimum=minimum,
                maximum=maximum,
            ),
        )

        essay, revisions = self._enforce_length(
            context, essay, context_blocks, target, minimum, maximum, warnings
        )

        word_count = count_words(essay)
        title = _extract_title(essay, topic)
        document = essay + render_sources_markdown(sources)

        logger.info(
            "ship30_essay generated an essay",
            extra={
                "skill": self.name,
                "word_count": word_count,
                "revisions": revisions,
                "source_count": len(sources),
            },
        )

        return SkillResult(
            answer=document,
            sources=sources,
            artifacts=[
                ArtifactDraft(
                    kind=ArtifactKind.MARKDOWN,
                    title=title,
                    content=document,
                    sources=sources,
                    metadata={
                        "skill": self.name,
                        "essay_word_count": word_count,
                        "target_word_count": target,
                        "revisions": revisions,
                    },
                )
            ],
            metadata={
                "word_count": word_count,
                "target_word_count": target,
                "within_target": minimum <= word_count <= maximum,
                "revisions": revisions,
                "grounded": bool(sources),
            },
            warnings=warnings,
        )

    def _enforce_length(
        self,
        context: SkillContext,
        essay: str,
        context_blocks: str,
        target: int,
        minimum: int,
        maximum: int,
        warnings: list[str],
    ) -> tuple[str, int]:
        """Nudge the draft toward the target word count with bounded revisions."""
        revisions = 0
        for _ in range(max(0, context.settings.essay_max_expansions)):
            actual = count_words(essay)
            if minimum <= actual <= maximum:
                return essay, revisions

            instruction = (
                "Expand the thinnest sections with more evidence and examples from the "
                "excerpts. Do not repeat yourself."
                if actual < minimum
                else "Tighten the prose and cut repetition without removing any section."
            )
            try:
                essay = self.generate(
                    context,
                    SYSTEM_PROMPT,
                    EXPANSION_PROMPT.format(
                        actual=actual,
                        minimum=minimum,
                        maximum=maximum,
                        target=target,
                        context=context_blocks,
                        instruction=instruction,
                        draft=essay,
                    ),
                )
                revisions += 1
            except Exception as exc:
                # A failed revision is not fatal: the first draft is still useful.
                logger.warning("Essay length revision failed: %s", exc)
                warnings.append(f"length_revision_failed: {exc}")
                break

        final = count_words(essay)
        if not minimum <= final <= maximum:
            warnings.append(
                f"word_count_off_target: {final} words (target {minimum}-{maximum})"
            )
        return essay, revisions


def render_sources_markdown(sources: list[SourceCitation]) -> str:
    if not sources:
        return (
            "\n\n---\n\n## Sources\n\n"
            "_No transcript excerpts were available for this essay; treat the claims "
            "above as unverified._\n"
        )

    lines = ["\n\n---\n\n## Sources\n"]
    for index, source in enumerate(sources, start=1):
        lines.append(
            f"{index}. **{source.document_title}** (chunk #{source.chunk_index}, "
            f"relevance {source.score:.2f})"
        )
    return "\n".join(lines) + "\n"


def _extract_title(essay: str, fallback: str) -> str:
    for line in essay.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()[:512]
    return fallback[:512]
