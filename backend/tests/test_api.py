from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.dependencies import get_run_store
from app.domain.schemas import RunStatus
from app.main import app
from app.services.run_store import RunStore


SAMPLE_TEXT = """第一章 开始
林夏收到第一封信。

第二章 剧院
林夏遇到周砚。

第三章 台词
林夏找到地址。
"""


def _client_with_store(tmp_path):
    settings = Settings(USE_MOCK_LLM=True, RUNS_DIR=tmp_path)
    store = RunStore(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_run_store] = lambda: store
    return TestClient(app), store


def test_schema_endpoint_returns_json_schema():
    client = TestClient(app)
    response = client.get("/api/schema/script")
    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "ScriptJson"
    assert "properties" in payload


def test_intake_rejects_less_than_three_chapters(tmp_path):
    client, _store = _client_with_store(tmp_path)
    try:
        response = client.post(
            "/api/runs/intake",
            data={"text": "第一章 开始\n只有一章。"},
        )
        assert response.status_code == 400
        assert "at least 3 chapter" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_compat_run_rejects_less_than_three_chapters(tmp_path):
    client, _store = _client_with_store(tmp_path)
    try:
        response = client.post(
            "/api/runs",
            data={"text": "第一章 开始\n只有一章。"},
        )
        assert response.status_code == 400
        assert "at least 3 chapter" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_intake_generates_adaptation_plan(tmp_path):
    client, store = _client_with_store(tmp_path)
    try:
        response = client.post("/api/runs/intake", data={"text": SAMPLE_TEXT})
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        manifest = store.read_manifest(run_id)
        assert manifest.status == RunStatus.planned
        assert "adaptation_plan.json" in manifest.artifacts
        assert "adaptation_plan.md" in manifest.artifacts
    finally:
        app.dependency_overrides.clear()


def test_generate_requires_completed_intake(tmp_path):
    client, store = _client_with_store(tmp_path)
    try:
        manifest = store.create_run(SAMPLE_TEXT)
        response = client.post(
            f"/api/runs/{manifest.run_id}/generate",
            json={"controls": {"format_type": "short_drama"}},
        )
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_generate_uses_author_controls_after_intake(tmp_path):
    client, store = _client_with_store(tmp_path)
    try:
        intake = client.post("/api/runs/intake", data={"text": SAMPLE_TEXT})
        run_id = intake.json()["run_id"]

        response = client.post(
            f"/api/runs/{run_id}/generate",
            json={
                "controls": {
                    "format_type": "short_drama",
                    "adaptation_scale": "faithful",
                    "style_focus": "psychological",
                    "preserve_items": ["保留林夏"],
                    "forbidden_changes": ["不要改变父亲失踪设定"],
                    "author_notes": "心理活动要转成动作。",
                }
            },
        )

        assert response.status_code == 200
        manifest = store.read_manifest(run_id)
        script = store.read_json(run_id, "script.json")
        assert manifest.status == RunStatus.succeeded
        assert script["adaptation_profile"]["adaptation_scale"] == "faithful"
        assert "script.yaml" in manifest.artifacts
    finally:
        app.dependency_overrides.clear()
