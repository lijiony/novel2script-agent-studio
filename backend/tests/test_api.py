from fastapi.testclient import TestClient

from app.main import app


def test_schema_endpoint_returns_json_schema():
    client = TestClient(app)
    response = client.get("/api/schema/script")
    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "ScriptJson"
    assert "properties" in payload
