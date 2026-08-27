from backend.tests.conftest import requires_db


def test_request_id_is_returned_and_echoed(client):
    generated = client.get("/health")
    assert generated.headers["x-request-id"]

    echoed = client.get("/health", headers={"X-Request-ID": "trace-123"})
    assert echoed.headers["x-request-id"] == "trace-123"


def test_metrics_endpoint_reports_counters_and_latency(client):
    client.get("/health")
    snapshot = client.get("/metrics").json()

    assert snapshot["counters"]["http_requests_total{method=GET,path=/health,status=200}"] >= 1
    request_latency = snapshot["latency_ms"]["http_request{method=GET,path=/health}"]
    assert request_latency["count"] >= 1
    assert request_latency["p95"] >= 0


@requires_db
def test_agent_turn_is_instrumented(ingested_client, session_id):
    ingested_client.post(
        f"/sessions/{session_id}/chat",
        json={"message": "What are growth loops?"},
    )
    snapshot = ingested_client.get("/metrics").json()

    assert snapshot["counters"]["agent_turns_total{intent=qa}"] == 1
    assert snapshot["counters"]["router_decisions_total{intent=qa,method=rules}"] == 1
    assert snapshot["counters"]["llm_calls_total{skill=grounded_qa}"] == 1
    assert snapshot["latency_ms"]["skill_run{skill=grounded_qa}"]["count"] == 1


@requires_db
def test_failures_are_counted(ingested_client, session_id, mock_llm_provider):
    mock_llm_provider.failure = RuntimeError("ollama down")
    ingested_client.post(
        f"/sessions/{session_id}/chat",
        json={"message": "What are growth loops?"},
    )
    counters = ingested_client.get("/metrics").json()["counters"]

    assert counters["llm_failures_total{skill=grounded_qa}"] == 1
    assert counters["skill_failures_total{skill=grounded_qa}"] == 1
    assert counters["app_errors_total{error_type=LLMError}"] == 1


def test_skills_endpoint_describes_the_agent_capabilities(client):
    skills = client.get("/skills").json()["skills"]
    names = {skill["intent"] for skill in skills}
    assert names == {"qa", "ship30_essay", "artifact_markdown", "artifact_html"}
    assert all(skill["description"] for skill in skills)
