"""Task router: decides which skill should handle a user turn.

Hybrid by design. Rules run first because they are deterministic, free and
cover the phrasings this product sees most ("write a Ship 30 essay about X",
"turn that into a landing page"). The LLM classifier is only consulted when the
rules are not confident, and any classifier failure degrades back to the rule
result — routing must never be the reason a request fails.
"""

import json
import logging
import re
from dataclasses import dataclass, field

from backend.app.agent.intents import Intent
from backend.app.config import Settings, get_settings
from backend.app.observability.metrics import METRICS
from backend.app.services.llm.base import LLMProvider
from backend.app.services.resilience import retry_call

logger = logging.getLogger(__name__)


@dataclass
class RouteDecision:
    intent: Intent
    confidence: float
    method: str
    rationale: str
    params: dict = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)


# (pattern, intent, weight). Weights are additive per matched pattern.
_RULES: list[tuple[str, Intent, float]] = [
    (r"\bship\s*-?\s*30\b|\bship30\b", Intent.SHIP30_ESSAY, 0.7),
    (r"\batomic essay\b", Intent.SHIP30_ESSAY, 0.7),
    (r"\bessay\b", Intent.SHIP30_ESSAY, 0.45),
    (r"\b1[,.]?250\s*(?:-|\s)?word", Intent.SHIP30_ESSAY, 0.5),
    (r"\bwrite (?:me )?(?:a|an|the) (?:long[- ]form|blog|op-?ed)\b", Intent.SHIP30_ESSAY, 0.4),
    (r"\bhtml\b", Intent.ARTIFACT_HTML, 0.7),
    (r"\bcss\b", Intent.ARTIFACT_HTML, 0.5),
    (r"\bweb\s?page\b|\blanding page\b|\bmicrosite\b|\bwebsite\b", Intent.ARTIFACT_HTML, 0.6),
    (r"\bstyled? page\b|\bhero section\b", Intent.ARTIFACT_HTML, 0.4),
    (r"\bmarkdown\b|\b\.md\b", Intent.ARTIFACT_MARKDOWN, 0.7),
    (
        r"\b(?:one[- ]pager|cheat ?sheet|checklist|playbook|brief|template|summary doc|"
        r"doc(?:ument)?)\b",
        Intent.ARTIFACT_MARKDOWN,
        0.45,
    ),
    (
        r"\b(?:create|generate|produce|draft|build|make|turn .* into)\b",
        Intent.ARTIFACT_MARKDOWN,
        0.15,
    ),
    (
        r"^\s*(?:what|why|how|when|who|which|where|is|are|does|do|can|should)\b",
        Intent.QA,
        0.5,
    ),
    (r"\?\s*$", Intent.QA, 0.35),
    (r"\b(?:explain|tell me about|summarize what|according to)\b", Intent.QA, 0.35),
]

_COMPILED_RULES = [
    (re.compile(pattern, re.IGNORECASE), intent, weight)
    for pattern, intent, weight in _RULES
]

_TOPIC_PATTERNS = [
    re.compile(r"\babout\s+(?P<topic>.+)$", re.IGNORECASE),
    re.compile(r"\bon\s+(?P<topic>.+)$", re.IGNORECASE),
]

CLASSIFIER_SYSTEM_PROMPT = """You classify user requests for a product-growth assistant.

Choose exactly one intent:
- "qa": the user asks a question and wants a grounded answer.
- "ship30_essay": the user wants a Ship 30 for 30 style long-form/atomic essay (~1,250 words).
- "artifact_markdown": the user wants a markdown document (brief, playbook, checklist, one-pager).
- "artifact_html": the user wants an HTML/CSS page, landing page or styled web output.

Respond with JSON only:
{"intent": "...", "confidence": 0.0-1.0, "rationale": "one short sentence"}"""


class TaskRouter:
    def __init__(self, llm: LLMProvider | None = None, settings: Settings | None = None) -> None:
        self.llm = llm
        self.settings = settings or get_settings()

    def route(self, message: str, history_text: str = "") -> RouteDecision:
        decision = self._route_by_rules(message)
        mode = self.settings.router_mode

        if mode == "rules" or (
            mode == "hybrid" and decision.confidence >= self.settings.router_confidence_threshold
        ):
            self._record(decision)
            return decision

        llm_decision = self._route_by_llm(message, history_text)
        final = llm_decision or (
            decision
            if mode == "hybrid"
            else RouteDecision(
                intent=Intent.QA,
                confidence=0.3,
                method="fallback",
                rationale="LLM routing unavailable; defaulting to grounded Q&A.",
            )
        )
        final.params.setdefault("topic", decision.params.get("topic"))
        self._record(final)
        return final

    # -- strategies -----------------------------------------------------

    def _route_by_rules(self, message: str) -> RouteDecision:
        scores: dict[Intent, float] = {intent: 0.0 for intent in Intent}
        matched: dict[Intent, list[str]] = {intent: [] for intent in Intent}

        for pattern, intent, weight in _COMPILED_RULES:
            if pattern.search(message):
                scores[intent] += weight
                matched[intent].append(pattern.pattern)

        # "write an essay as a web page" should produce an HTML page, not an essay:
        # the output format wins over the content style.
        if scores[Intent.ARTIFACT_HTML] > 0 and scores[Intent.SHIP30_ESSAY] > 0:
            scores[Intent.ARTIFACT_HTML] += 0.3

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_intent, top_score = ranked[0]
        runner_up_score = ranked[1][1]

        if top_score <= 0:
            return RouteDecision(
                intent=Intent.QA,
                confidence=0.3,
                method="rules",
                rationale="No routing keywords matched; defaulting to grounded Q&A.",
                params={"topic": _extract_topic(message)},
                scores={intent.value: round(score, 3) for intent, score in scores.items()},
            )

        margin = top_score - runner_up_score
        confidence = min(0.95, round(min(top_score, 1.0) * 0.7 + min(margin, 0.5) * 0.6, 3))

        return RouteDecision(
            intent=top_intent,
            confidence=confidence,
            method="rules",
            rationale=f"Matched {len(matched[top_intent])} rule(s) for {top_intent.value}.",
            params={"topic": _extract_topic(message)},
            scores={intent.value: round(score, 3) for intent, score in scores.items()},
        )

    def _route_by_llm(self, message: str, history_text: str) -> RouteDecision | None:
        llm = self.llm
        if llm is None:
            return None

        prompt = (
            f"Conversation so far:\n{history_text or '(none)'}\n\n"
            f"Latest user message:\n{message}\n\nClassify it."
        )
        try:
            raw = retry_call(
                "router.classify",
                lambda: llm.generate(CLASSIFIER_SYSTEM_PROMPT, prompt),
                attempts=min(2, self.settings.llm_max_attempts),
            )
            payload = _parse_json_object(raw)
            intent = Intent(str(payload["intent"]).strip())
        except Exception as exc:
            logger.warning("LLM routing failed, falling back to rules: %s", exc)
            METRICS.increment("router_llm_failures_total")
            return None

        confidence = payload.get("confidence", 0.6)
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.6

        return RouteDecision(
            intent=intent,
            confidence=confidence,
            method="llm",
            rationale=str(payload.get("rationale", "Classified by LLM."))[:280],
            params={"topic": _extract_topic(message)},
        )

    @staticmethod
    def _record(decision: RouteDecision) -> None:
        METRICS.increment(
            "router_decisions_total",
            intent=decision.intent.value,
            method=decision.method,
        )
        logger.info(
            "Routed request to %s (%s, confidence=%.2f)",
            decision.intent.value,
            decision.method,
            decision.confidence,
            extra={
                "intent": decision.intent.value,
                "router_method": decision.method,
                "router_confidence": decision.confidence,
            },
        )


def _parse_json_object(raw: str) -> dict:
    text = raw.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON object in classifier output: {text[:120]!r}")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict) or "intent" not in payload:
        raise ValueError("Classifier output missing 'intent'")
    return payload


def _extract_topic(message: str) -> str | None:
    for pattern in _TOPIC_PATTERNS:
        match = pattern.search(message.strip().rstrip("?."))
        if match:
            topic = match.group("topic").strip()
            if topic:
                return topic[:300]
    return None
