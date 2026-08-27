from backend.tests.conftest import requires_db

pytestmark = requires_db


def _generate(client, session_id, kind: str, instruction: str = "Growth loops overview"):
    response = client.post(
        f"/sessions/{session_id}/artifacts",
        json={"instruction": instruction, "kind": kind},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_generate_artifact_endpoint_forces_the_kind(ingested_client, session_id):
    body = _generate(ingested_client, session_id, "html")
    assert body["routing"]["method"] == "explicit"
    assert body["artifacts"][0]["kind"] == "html"


def test_list_filter_and_delete_artifacts(ingested_client, session_id):
    markdown = _generate(ingested_client, session_id, "markdown")["artifacts"][0]
    html = _generate(ingested_client, session_id, "html")["artifacts"][0]

    all_artifacts = ingested_client.get("/artifacts").json()
    assert {a["id"] for a in all_artifacts} >= {markdown["id"], html["id"]}

    only_html = ingested_client.get("/artifacts", params={"kind": "html"}).json()
    assert [a["id"] for a in only_html] == [html["id"]]

    scoped = ingested_client.get(f"/sessions/{session_id}/artifacts").json()
    assert len(scoped) == 2
    assert "content" not in scoped[0]

    assert ingested_client.delete(f"/artifacts/{markdown['id']}").status_code == 204
    assert ingested_client.get(f"/artifacts/{markdown['id']}").status_code == 404
    assert len(ingested_client.get(f"/sessions/{session_id}/artifacts").json()) == 1


def test_artifact_pagination(ingested_client, session_id):
    for _ in range(3):
        _generate(ingested_client, session_id, "markdown")

    page = ingested_client.get("/artifacts", params={"limit": 2}).json()
    assert len(page) == 2
    second = ingested_client.get("/artifacts", params={"limit": 2, "offset": 2}).json()
    assert len(second) == 1
    assert {a["id"] for a in page}.isdisjoint({a["id"] for a in second})


def test_markdown_raw_endpoint(ingested_client, session_id):
    artifact = _generate(ingested_client, session_id, "markdown")["artifacts"][0]
    raw = ingested_client.get(f"/artifacts/{artifact['id']}/raw")
    assert raw.headers["content-type"].startswith("text/markdown")
    assert raw.text.startswith("# ")


def test_unknown_artifact_returns_404(ingested_client):
    missing = "00000000-0000-0000-0000-000000000000"
    assert ingested_client.get(f"/artifacts/{missing}").status_code == 404
    assert ingested_client.get(f"/artifacts/{missing}/raw").status_code == 404
    assert ingested_client.delete(f"/artifacts/{missing}").status_code == 404


def test_invalid_artifact_kind_is_rejected(ingested_client, session_id):
    response = ingested_client.post(
        f"/sessions/{session_id}/artifacts",
        json={"instruction": "anything", "kind": "pdf"},
    )
    assert response.status_code == 422
