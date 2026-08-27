def test_ingest_document(client):
    payload = {
        "title": "Test Transcript",
        "source": "test.txt",
        "content": "Growth loops compound over time when each cycle feeds the next.",
        "metadata": {"guest": "Test Guest"},
    }
    response = client.post("/documents/ingest", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Transcript"
    assert data["chunk_count"] >= 1

    duplicate = client.post("/documents/ingest", json=payload)
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == data["id"]


def test_ingest_directory(client):
    response = client.post("/documents/ingest-directory")
    assert response.status_code == 200
    data = response.json()
    assert len(data["ingested"]) >= 2
