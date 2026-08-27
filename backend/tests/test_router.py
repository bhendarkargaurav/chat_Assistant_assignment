import pytest

from backend.app.agent.intents import Intent
from backend.app.agent.router import TaskRouter
from backend.app.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("What are growth loops?", Intent.QA),
        ("How did Elena Verna think about PLG?", Intent.QA),
        ("Explain the difference between funnels and loops", Intent.QA),
        ("Write a Ship 30 for 30 essay about growth loops", Intent.SHIP30_ESSAY),
        ("I need a 1,250 word atomic essay on retention", Intent.SHIP30_ESSAY),
        ("Draft an essay on product-market fit", Intent.SHIP30_ESSAY),
        ("Turn that into an HTML landing page", Intent.ARTIFACT_HTML),
        ("Build a styled web page with CSS about onboarding", Intent.ARTIFACT_HTML),
        ("Give me a markdown checklist for launch week", Intent.ARTIFACT_MARKDOWN),
        ("Create a one-pager brief on activation metrics", Intent.ARTIFACT_MARKDOWN),
    ],
)
def test_rule_routing(settings, message, expected):
    settings.router_mode = "rules"
    decision = TaskRouter(llm=None, settings=settings).route(message)
    assert decision.intent is expected
    assert decision.method == "rules"


def test_output_format_beats_content_style(settings):
    settings.router_mode = "rules"
    decision = TaskRouter(llm=None, settings=settings).route(
        "Write an essay about growth loops as an HTML page"
    )
    assert decision.intent is Intent.ARTIFACT_HTML


def test_topic_extraction(settings):
    decision = TaskRouter(llm=None, settings=settings).route(
        "Write a Ship 30 essay about retention loops in B2B"
    )
    assert decision.params["topic"] == "retention loops in B2B"


def test_ambiguous_message_falls_through_to_llm(settings, mock_llm_provider):
    settings.router_mode = "hybrid"
    mock_llm_provider.responses["You classify user requests"] = (
        '{"intent": "artifact_html", "confidence": 0.9, "rationale": "Wants a page."}'
    )
    decision = TaskRouter(llm=mock_llm_provider, settings=settings).route("growth stuff")
    assert decision.intent is Intent.ARTIFACT_HTML
    assert decision.method == "llm"
    assert decision.confidence == 0.9


def test_llm_routing_failure_degrades_to_rules(settings, mock_llm_provider):
    settings.router_mode = "hybrid"
    settings.retry_base_delay_seconds = 0
    mock_llm_provider.failure = RuntimeError("model unavailable")
    decision = TaskRouter(llm=mock_llm_provider, settings=settings).route("growth stuff")
    assert decision.intent is Intent.QA
    assert decision.method == "rules"


def test_unparsable_classifier_output_degrades_to_rules(settings, mock_llm_provider):
    settings.router_mode = "hybrid"
    settings.retry_base_delay_seconds = 0
    mock_llm_provider.responses["You classify user requests"] = "I think it's a question!"
    decision = TaskRouter(llm=mock_llm_provider, settings=settings).route("growth stuff")
    assert decision.method == "rules"


def test_unknown_intent_from_classifier_degrades_to_rules(settings, mock_llm_provider):
    settings.router_mode = "hybrid"
    settings.retry_base_delay_seconds = 0
    mock_llm_provider.responses["You classify user requests"] = '{"intent": "make_coffee"}'
    decision = TaskRouter(llm=mock_llm_provider, settings=settings).route("growth stuff")
    assert decision.intent is Intent.QA
    assert decision.method == "rules"


def test_confident_rule_match_skips_the_llm(settings, mock_llm_provider):
    settings.router_mode = "hybrid"
    TaskRouter(llm=mock_llm_provider, settings=settings).route(
        "Write a Ship 30 for 30 essay about growth loops"
    )
    assert mock_llm_provider.calls == []
