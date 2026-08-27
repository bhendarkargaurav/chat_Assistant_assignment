def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "Lenny Growth Assistant" in data["service"]


def test_ready(client):
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"ok", "degraded"}
    assert "checks" in data
    assert data["checks"]["database"] == "ok"
