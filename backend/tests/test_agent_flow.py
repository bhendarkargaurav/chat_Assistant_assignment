"""Critical-path integration tests: user turn -> router -> skill -> artifact."""

from backend.app.services.sanitize import assert_safe_html
from backend.tests.conftest import requires_db

pytestmark = requires_db


def test_qa_turn_is_grounded_and_routed(ingested_client, session_id):
    response = ingested_client.post(
        f"/sessions/{session_id}/chat",
        json={"message": "What are growth loops?"},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["skill"] == "grounded_qa"
    assert body["routing"]["intent"] == "qa"
    assert body["sources"]
    assert body["sources"][0]["document_title"] == "Growth Loops"
    assert body["artifacts"] == []
    assert "growth" in body["answer"].lower()


def test_ship30_turn_produces_a_persisted_markdown_essay(
    ingested_client, session_id, mock_llm_provider
):
    response = ingested_client.post(
        f"/sessions/{session_id}/chat",
        json={"message": "Write a Ship 30 for 30 essay about growth loops"},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["skill"] == "ship30_essay"
    assert body["routing"]["intent"] == "ship30_essay"
    assert body["metadata"]["within_target"] is True
    assert 1100 <= body["metadata"]["word_count"] <= 1400
    assert "## Sources" in body["answer"]

    assert len(body["artifacts"]) == 1
    artifact = body["artifacts"][0]
    assert artifact["kind"] == "markdown"
    assert artifact["skill"] == "ship30_essay"

    stored = ingested_client.get(f"/artifacts/{artifact['id']}").json()
    assert stored["content"].startswith("# ")
    assert stored["sources"]
    assert stored["artifact_metadata"]["target_word_count"] == 1250


def test_ship30_revises_a_short_draft_toward_the_target(
    ingested_client, session_id, mock_llm_provider
):
    mock_llm_provider.essay_words = [400, 1250]
    body = ingested_client.post(
        f"/sessions/{session_id}/chat",
        json={"message": "Write a Ship 30 for 30 essay about growth loops"},
    ).json()

    assert body["metadata"]["revisions"] == 1
    assert body["metadata"]["within_target"] is True


def test_ship30_warns_when_it_cannot_hit_the_target(
    ingested_client, session_id, mock_llm_provider
):
    mock_llm_provider.essay_words = [300, 350]
    body = ingested_client.post(
        f"/sessions/{session_id}/chat",
        json={"message": "Write a Ship 30 for 30 essay about growth loops"},
    ).json()

    assert body["metadata"]["within_target"] is False
    assert any(w.startswith("word_count_off_target") for w in body["warnings"])


def test_markdown_artifact_turn(ingested_client, session_id):
    body = ingested_client.post(
        f"/sessions/{session_id}/chat",
        json={"message": "Create a markdown playbook on growth loops"},
    ).json()

    assert body["skill"] == "markdown_artifact"
    assert body["artifacts"][0]["kind"] == "markdown"

    stored = ingested_client.get(f"/artifacts/{body['artifacts'][0]['id']}").json()
    assert stored["content"].startswith("# Growth Loops Playbook")
    assert "## Sources" in stored["content"]
    assert stored["sources"]


def test_html_artifact_turn_is_sanitized_and_served_safely(
    ingested_client, session_id, mock_llm_provider
):
    mock_llm_provider.responses["standalone, self-contained HTML pages"] = (
        "<!DOCTYPE html><html><head><style>body { color: #111; }</style></head>"
        "<body><h1>Growth Loops</h1><script>alert('xss')</script>"
        "<p onclick=\"alert(1)\">Loops compound.</p></body></html>"
    )
    body = ingested_client.post(
        f"/sessions/{session_id}/chat",
        json={"message": "Turn that into an HTML landing page"},
    ).json()

    assert body["skill"] == "html_artifact"
    artifact_id = body["artifacts"][0]["id"]
    stored = ingested_client.get(f"/artifacts/{artifact_id}").json()
    assert "<script" not in stored["content"]
    assert "onclick" not in stored["content"]
    assert "Growth Loops" in stored["content"]
    assert_safe_html(stored["content"])

    raw = ingested_client.get(f"/artifacts/{artifact_id}/raw")
    assert raw.headers["content-type"].startswith("text/html")
    assert raw.headers["x-content-type-options"] == "nosniff"
    assert raw.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in raw.headers["content-security-policy"]


def test_forced_intent_bypasses_the_router(ingested_client, session_id):
    body = ingested_client.post(
        f"/sessions/{session_id}/chat",
        json={"message": "growth loops", "intent": "artifact_html"},
    ).json()

    assert body["routing"]["method"] == "explicit"
    assert body["skill"] == "html_artifact"


def test_generation_is_conversation_aware(ingested_client, session_id, mock_llm_provider):
    ingested_client.post(
        f"/sessions/{session_id}/chat",
        json={"message": "What are growth loops?"},
    )
    ingested_client.post(
        f"/sessions/{session_id}/chat",
        json={"message": "Turn that answer into a markdown brief"},
    )

    markdown_prompts = [
        user for system, user in mock_llm_provider.calls
        if "polished markdown documents" in system
    ]
    assert markdown_prompts
    assert "What are growth loops?" in markdown_prompts[-1]
    assert "self-reinforcing cycles" in markdown_prompts[-1]


def test_chat_history_survives_the_turn(ingested_client, session_id):
    ingested_client.post(
        f"/sessions/{session_id}/chat",
        json={"message": "What are growth loops?"},
    )
    detail = ingested_client.get(f"/sessions/{session_id}").json()
    roles = [message["role"] for message in detail["messages"]]
    assert roles == ["user", "assistant"]


def test_chat_on_missing_session_returns_404(ingested_client):
    response = ingested_client.post(
        "/sessions/00000000-0000-0000-0000-000000000000/chat",
        json={"message": "hello"},
    )
    assert response.status_code == 404
