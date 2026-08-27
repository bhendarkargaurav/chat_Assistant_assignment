"""Artifact-producing skills: markdown documents and standalone HTML/CSS pages.

Both skills are conversation-aware — "turn that into a landing page" resolves
against the last assistant turn — and both attach the retrieved transcript
chunks as source attribution.
"""

import html
import logging
import re

from backend.app.db.models import ArtifactKind
from backend.app.exceptions import ArtifactError
from backend.app.schemas.source import SourceCitation
from backend.app.services.sanitize import sanitize_html_document
from backend.app.skills.base import (
    ArtifactDraft,
    Skill,
    SkillContext,
    SkillResult,
    format_context_blocks,
    strip_code_fence,
)
from backend.app.skills.ship30 import render_sources_markdown

logger = logging.getLogger(__name__)

MARKDOWN_SYSTEM_PROMPT = """You produce polished markdown documents for the Lenny Growth
Assistant (briefs, playbooks, checklists, one-pagers).

Rules:
- Start with a single `#` title, then use `##` sections. Use lists and tables where they
  make the content scannable.
- Ground factual claims in the supplied transcript excerpts and cite them inline as
  [Source: title (#chunk_index)]. Never invent metrics, quotes or company names.
- If the conversation refers to earlier content ("that", "the answer above"), build on it.
- Do not add a sources section; it is appended automatically.
- Return markdown only — no commentary, no code fences."""

HTML_SYSTEM_PROMPT = """You produce standalone, self-contained HTML pages with embedded CSS
for the Lenny Growth Assistant.

Rules:
- Return a complete `<!DOCTYPE html>` document with a single `<style>` block in the head.
- Layout with semantic elements (header, main, section, article, footer) and modern,
  readable CSS: system font stack, generous spacing, responsive max-width container.
- No JavaScript, no external requests (no <script>, <link>, <iframe>, remote fonts or
  images). Anything of that kind is stripped before the page is stored.
- Ground the copy in the supplied transcript excerpts; cite them as visible text such as
  "Source: title (#chunk_index)". Never invent metrics, quotes or company names.
- Return HTML only — no commentary, no code fences."""

USER_PROMPT = """Conversation so far (use it to stay consistent and to resolve references
such as "that" or "the essay above"):
{history}

Most recent assistant output (may be the thing the user wants converted):
{previous}

Transcript excerpts to ground the content in:
{context}

User request:
{request}

{instruction}"""


class _ArtifactSkill(Skill):
    kind: ArtifactKind
    system_prompt: str
    instruction: str

    def run(self, context: SkillContext) -> SkillResult:
        warnings: list[str] = []
        sources = self.retrieve(context, context.message, warnings=warnings)
        previous = context.last_assistant_message() or "(none)"

        raw = self.generate(
            context,
            self.system_prompt,
            USER_PROMPT.format(
                history=context.history_text(),
                previous=previous[:4000],
                context=format_context_blocks(sources),
                request=context.message,
                instruction=self.instruction,
            ),
        )

        content = self.build(strip_code_fence(raw), sources, context)
        self._enforce_size(content, context)
        title = self.extract_title(content, context.message)

        logger.info(
            "%s produced an artifact",
            self.name,
            extra={
                "skill": self.name,
                "artifact_kind": self.kind.value,
                "source_count": len(sources),
                "content_bytes": len(content.encode("utf-8")),
            },
        )

        return SkillResult(
            answer=self.summary(title, len(sources)),
            sources=sources,
            artifacts=[
                ArtifactDraft(
                    kind=self.kind,
                    title=title,
                    content=content,
                    sources=sources,
                    metadata={"skill": self.name, "conversation_aware": previous != "(none)"},
                )
            ],
            metadata={"artifact_kind": self.kind.value, "grounded": bool(sources)},
            warnings=warnings,
        )

    def build(
        self, raw: str, sources: list[SourceCitation], context: SkillContext
    ) -> str:
        raise NotImplementedError

    def extract_title(self, content: str, fallback: str) -> str:
        raise NotImplementedError

    def summary(self, title: str, source_count: int) -> str:
        grounding = (
            f" grounded in {source_count} transcript excerpt"
            f"{'s' if source_count != 1 else ''}"
            if source_count
            else " (no matching transcript excerpts were found, so it is ungrounded)"
        )
        return f'Generated the {self.kind.value} artifact "{title}"{grounding}.'

    def _enforce_size(self, content: str, context: SkillContext) -> None:
        size = len(content.encode("utf-8"))
        if size > context.settings.artifact_max_bytes:
            raise ArtifactError(
                f"Generated artifact is {size} bytes, over the "
                f"{context.settings.artifact_max_bytes} byte limit"
            )
        if not content.strip():
            raise ArtifactError("Generated artifact was empty")


class MarkdownArtifactSkill(_ArtifactSkill):
    name = "markdown_artifact"
    description = (
        "Generate a markdown document (brief, playbook, checklist, one-pager) grounded "
        "in transcripts and the current conversation."
    )
    kind = ArtifactKind.MARKDOWN
    system_prompt = MARKDOWN_SYSTEM_PROMPT
    instruction = "Write the markdown document now."

    def build(
        self, raw: str, sources: list[SourceCitation], context: SkillContext
    ) -> str:
        return raw + render_sources_markdown(sources)

    def extract_title(self, content: str, fallback: str) -> str:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()[:512]
        return fallback[:512]


class HtmlArtifactSkill(_ArtifactSkill):
    name = "html_artifact"
    description = (
        "Generate a self-contained, sanitized HTML page with embedded CSS grounded in "
        "transcripts and the current conversation."
    )
    kind = ArtifactKind.HTML
    system_prompt = HTML_SYSTEM_PROMPT
    instruction = "Write the HTML page now."

    def build(
        self, raw: str, sources: list[SourceCitation], context: SkillContext
    ) -> str:
        title = self._raw_title(raw) or context.message[:120]
        body = sanitize_html_document(raw)
        if not body:
            raise ArtifactError("Generated HTML was empty after sanitization")
        return _wrap_html_document(title, body + _render_sources_html(sources))

    def extract_title(self, content: str, fallback: str) -> str:
        return self._raw_title(content) or fallback[:512]

    @staticmethod
    def _raw_title(markup: str) -> str | None:
        match = re.search(r"<title[^>]*>(.*?)</title>", markup, re.IGNORECASE | re.DOTALL)
        if match and match.group(1).strip():
            return html.unescape(match.group(1).strip())[:512]
        match = re.search(r"<h1[^>]*>(.*?)</h1>", markup, re.IGNORECASE | re.DOTALL)
        if match and match.group(1).strip():
            return html.unescape(re.sub(r"<[^>]+>", "", match.group(1)).strip())[:512]
        return None


def _render_sources_html(sources: list[SourceCitation]) -> str:
    if not sources:
        return (
            '<footer class="sources"><h2>Sources</h2><p>No transcript excerpts were '
            "available for this page; treat the claims above as unverified.</p></footer>"
        )
    items = "".join(
        f"<li>{html.escape(source.document_title)} (chunk #{source.chunk_index}, "
        f"relevance {source.score:.2f})</li>"
        for source in sources
    )
    return f'<footer class="sources"><h2>Sources</h2><ol>{items}</ol></footer>'


def _wrap_html_document(title: str, body: str) -> str:
    """Wrap sanitized markup in a minimal document shell.

    Sanitization strips <html>/<head>/<meta>, so the shell is rebuilt here from
    values we control.
    """
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )
