def test_create_and_get_session(client):
    create_response = client.post("/sessions", json={"title": "Growth chat"})
    assert create_response.status_code == 201
    session = create_response.json()
    assert session["title"] == "Growth chat"
    assert "id" in session

    get_response = client.get(f"/sessions/{session['id']}")
    assert get_response.status_code == 200
    detail = get_response.json()
    assert detail["id"] == session["id"]
    assert detail["messages"] == []


def test_list_sessions(client):
    client.post("/sessions", json={"title": "Session A"})
    response = client.get("/sessions")
    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) >= 1


def test_get_missing_session_returns_404(client):
    response = client.get("/sessions/00000000-0000-0000-0000-000000000001")
    assert response.status_code == 404
