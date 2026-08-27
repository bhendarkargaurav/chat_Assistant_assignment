def test_chat_grounded_response(client):
    client.post(
        "/documents/ingest",
        json={
            "title": "Growth Loops",
            "source": "growth.txt",
            "content": (
                "Growth loops are self-reinforcing cycles where output becomes input. "
                "Referral loops and content loops are common in product-led growth."
            ),
        },
    )

    session_response = client.post("/sessions", json={"title": "Chat"})
    session_id = session_response.json()["id"]

    chat_response = client.post(
        f"/sessions/{session_id}/chat",
        json={"message": "What are growth loops?"},
    )
    assert chat_response.status_code == 200
    data = chat_response.json()
    assert data["session_id"] == session_id
    assert "Growth loops" in data["answer"] or "growth" in data["answer"].lower()
    assert data["provider"] == "ollama"
    assert isinstance(data["sources"], list)

    history = client.get(f"/sessions/{session_id}")
    messages = history.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
