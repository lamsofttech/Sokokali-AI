from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.container import Container, build_container
from app.main import create_app


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "Sokokali", "version": "0.2.0"}
    assert "X-Request-ID" in response.headers


def test_ready(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_status_reports_simulated_provider(client: TestClient) -> None:
    body = client.get("/api/v1/status").json()
    assert body["service"] == "Sokokali"
    components = {c["name"]: c for c in body["components"]}
    assert "SIMULATED" in components["sports_provider"]["detail"]


def test_fixtures(client: TestClient) -> None:
    body = client.get("/api/v1/fixtures", params={"limit": 3}).json()
    assert len(body["fixtures"]) == 3
    assert body["freshness"]["is_simulated"] is True
    kickoffs = [f["kickoff"] for f in body["fixtures"]]
    assert kickoffs == sorted(kickoffs)


def test_fixtures_limit_validation(client: TestClient) -> None:
    assert client.get("/api/v1/fixtures", params={"limit": 0}).status_code == 422


def test_prediction_endpoint(client: TestClient) -> None:
    match_id = client.get("/api/v1/fixtures").json()["fixtures"][0]["match_id"]
    body = client.get(f"/api/v1/predictions/{match_id}").json()
    p = body["probabilities"]
    assert abs(p["home_win"] + p["draw"] + p["away_win"] - 1) < 1e-6
    for key in ("match_id", "home_team", "away_team", "predicted_at", "freshness", "model_version", "key_factors"):
        assert key in body


def test_prediction_unknown_match(client: TestClient) -> None:
    assert client.get("/api/v1/predictions/sim-nope-999").status_code == 404


def test_chat_swahili_prediction(client: TestClient) -> None:
    response = client.post("/api/v1/chat", json={"message": "Sokokali, Arsenal na Chelsea nani atashinda?"})
    assert response.status_code == 200
    body = response.json()
    assert body["language"] == "sw"
    assert body["intent"] == "prediction"
    assert body["teams"] == ["Arsenal", "Chelsea"]
    assert body["prediction"]["home_team"] == "Arsenal"
    assert body["is_simulated_data"] is True
    assert body["reply"].startswith("Wadau!")
    assert "si uhakika" in body["reply"]
    assert "majaribio" in body["reply"]


def test_chat_greeting_has_no_simulated_notice(client: TestClient) -> None:
    body = client.post("/api/v1/chat", json={"message": "Hello Sokokali"}).json()
    assert body["intent"] == "greeting"
    assert body["is_simulated_data"] is False
    assert "Sokokali" in body["reply"]


def test_chat_does_not_invent_unscheduled_match(client: TestClient) -> None:
    body = client.post("/api/v1/chat", json={"message": "Arsenal vs Gor Mahia who will win?"}).json()
    assert body["intent"] == "prediction"
    assert body["prediction"] is None
    assert "won't make up" in body["reply"]


def test_chat_follow_up_uses_conversation_context(client: TestClient) -> None:
    viewer = {"viewer_id": "viewer-1"}
    client.post("/api/v1/chat", json={"message": "Gor Mahia vs AFC Leopards", **viewer})
    body = client.post("/api/v1/chat", json={"message": "So who will win?", **viewer}).json()
    assert body["teams"] == ["Gor Mahia", "AFC Leopards"]
    assert body["prediction"] is not None


def test_chat_context_is_per_viewer(client: TestClient) -> None:
    client.post("/api/v1/chat", json={"message": "Gor Mahia vs AFC Leopards", "viewer_id": "a"})
    body = client.post("/api/v1/chat", json={"message": "So who will win?", "viewer_id": "b"}).json()
    assert body["teams"] == []
    assert body["prediction"] is None


def test_chat_moderation(client: TestClient, container: Container) -> None:
    body = client.post("/api/v1/chat", json={"message": "Call me 0712345678", "viewer_id": "v2"}).json()
    assert body["moderated"] is True
    assert body["intent"] == "moderated"
    assert container.memory.history("v2") == []  # personal data is not retained


def test_chat_fixtures_and_results(client: TestClient) -> None:
    fixtures = client.post("/api/v1/chat", json={"message": "fixtures"}).json()
    assert fixtures["intent"] == "fixtures"
    assert "Arsenal vs Chelsea" in fixtures["reply"]
    results = client.post("/api/v1/chat", json={"message": "Arsenal Chelsea last result"}).json()
    assert results["intent"] == "results"
    assert "Arsenal" in results["reply"] and "Chelsea" in results["reply"]


def test_chat_guarantee_request_is_answered_responsibly(client: TestClient) -> None:
    body = client.post("/api/v1/chat", json={"message": "Nipe sure bet ya leo"}).json()
    assert body["intent"] == "guarantee_request"
    assert body["prediction"] is None


def test_chat_validation(client: TestClient) -> None:
    assert client.post("/api/v1/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/v1/chat", json={"message": "   "}).status_code == 422
    assert client.post("/api/v1/chat", json={"message": "x" * 501}).status_code == 422
    assert client.post("/api/v1/chat", json={"message": "hi", "viewer_id": "bad id!"}).status_code == 422


def test_chat_rate_limit(settings: Settings) -> None:
    limited = settings.model_copy(update={"chat_rate_limit_per_minute": 2})
    with TestClient(create_app(limited, build_container(limited))) as client:
        codes = [client.post("/api/v1/chat", json={"message": "hi"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_openapi_docs_available(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    for path in ("/health", "/api/v1/status", "/api/v1/chat", "/api/v1/fixtures", "/api/v1/predictions/{match_id}"):
        assert path in paths
