import pytest
from sqlalchemy.exc import OperationalError

from backend.app.config import get_settings
from backend.app.exceptions import ArtifactError, LLMError
from backend.app.services import artifacts as artifacts_module
from backend.app.services import rag as rag_module
from backend.app.services.resilience import retry_call
from backend.app.skills.base import Skill, SkillContext
from backend.tests.conftest import requires_db


def test_retry_call_succeeds_after_transient_failures():
    attempts = {"n": 0}

    def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("boom")
        return "ok"

    assert retry_call("test", flaky, attempts=3, base_delay=0) == "ok"
    assert attempts["n"] == 3


def test_retry_call_reraises_after_budget():
    attempts = {"n": 0}

    def always_fails() -> str:
        attempts["n"] += 1
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        retry_call("test", always_fails, attempts=2, base_delay=0)
    assert attempts["n"] == 2


def test_retry_call_does_not_retry_unlisted_exceptions():
    attempts = {"n": 0}

    def fails(_=None) -> str:
        attempts["n"] += 1
        raise KeyError("nope")

    with pytest.raises(KeyError):
        retry_call("test", fails, attempts=3, base_delay=0, retry_on=(ValueError,))
    assert attempts["n"] == 1


class _Nothing(Skill):
    name = "test_skill"
    description = "test"

    def run(self, context: SkillContext):  # pragma: no cover - unused
        raise NotImplementedError


def test_empty_llm_output_is_an_llm_error(mock_llm_provider):
    settings = get_settings()
    settings_copy = settings.model_copy(update={"llm_max_attempts": 1})
    mock_llm_provider.responses["anything"] = "   "
    context = SkillContext(
        message="anything",
        session_id=None,
        history=[],
        rag=None,
        llm=mock_llm_provider,
        settings=settings_copy,
    )
    with pytest.raises(LLMError):
        _Nothing().generate(context, "system", "anything")


@requires_db
def test_llm_outage_returns_502(ingested_client, session_id, mock_llm_provider, monkeypatch):
    monkeypatch.setattr(get_settings(), "retry_base_delay_seconds", 0, raising=False)
    mock_llm_provider.failure = RuntimeError("ollama down")
    response = ingested_client.post(
        f"/sessions/{session_id}/chat",
        json={"message": "What are growth loops?"},
    )
    assert response.status_code == 502
    body = response.json()
    assert body["error_type"] == "LLMError"
    assert body["request_id"]


@requires_db
def test_user_message_is_kept_when_the_llm_fails(
    ingested_client, session_id, mock_llm_provider, monkeypatch
):
    monkeypatch.setattr(get_settings(), "retry_base_delay_seconds", 0, raising=False)
    mock_llm_provider.failure = RuntimeError("ollama down")
    ingested_client.post(
        f"/sessions/{session_id}/chat", json={"message": "What are growth loops?"}
    )

    detail = ingested_client.get(f"/sessions/{session_id}").json()
    assert [m["role"] for m in detail["messages"]] == ["user"]


@requires_db
def test_retrieval_outage_degrades_with_a_warning(ingested_client, session_id, monkeypatch):
    def broken_retrieve(self, query, top_k=None):
        raise OperationalError("SELECT 1", {}, Exception("pgvector unavailable"))

    monkeypatch.setattr(rag_module.RAGService, "retrieve", broken_retrieve)

    body = ingested_client.post(
        f"/sessions/{session_id}/chat",
        json={"message": "What are growth loops?"},
    ).json()

    assert body["sources"] == []
    assert any(w.startswith("retrieval_unavailable") for w in body["warnings"])
    assert body["answer"]


@requires_db
def test_no_matching_sources_is_reported(client, session_id_without_documents):
    body = client.post(
        f"/sessions/{session_id_without_documents}/chat",
        json={"message": "What are growth loops?"},
    ).json()
    assert "no_matching_sources" in body["warnings"]


@requires_db
def test_artifact_persistence_failure_keeps_the_generated_content(
    ingested_client, session_id, monkeypatch
):
    def broken_create(self, draft, session_id, message_id, skill):
        raise artifacts_module.PersistenceError("disk full")

    monkeypatch.setattr(artifacts_module.ArtifactService, "create_from_draft", broken_create)

    body = ingested_client.post(
        f"/sessions/{session_id}/chat",
        json={"message": "Create a markdown playbook on growth loops"},
    ).json()

    assert body["artifacts"] == []
    assert any(w.startswith("artifact_not_persisted") for w in body["warnings"])
    assert body["answer"]


@requires_db
def test_unsafe_html_is_rejected_before_storage(ingested_client, session_id, mock_llm_provider):
    mock_llm_provider.responses["standalone, self-contained HTML pages"] = (
        "<script>alert(1)</script>"
    )
    response = ingested_client.post(
        f"/sessions/{session_id}/chat",
        json={"message": "Turn that into an HTML landing page"},
    )
    assert response.status_code == 422
    assert response.json()["error_type"] == ArtifactError.__name__
