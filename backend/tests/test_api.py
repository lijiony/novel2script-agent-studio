from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.dependencies import get_run_store
from app.domain.schemas import RunStatus
from app.main import app
from app.services.llm_client import LlmClient
from app.services.run_store import RunStore


SAMPLE_TEXT = """第一章 开始
林夏收到第一封信。

第二章 剧院
林夏遇到周砚。

第三章 台词
林夏找到地址。
"""


def _client_with_store(tmp_path):
    settings = Settings(
        USE_MOCK_LLM=True,
        OPENAI_API_KEY=None,
        OPENAI_BASE_URL=None,
        RUNS_DIR=tmp_path,
    )
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


def test_llm_status_defaults_to_mock(tmp_path):
    client, _store = _client_with_store(tmp_path)
    try:
        response = client.get("/api/llm/status")
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "mock"
        assert payload["api_key_configured"] is False
        assert "api_key" not in payload
    finally:
        app.dependency_overrides.clear()


def test_llm_test_reports_missing_key_in_real_mode(tmp_path):
    settings = Settings(USE_MOCK_LLM=False, OPENAI_API_KEY=None, RUNS_DIR=tmp_path)
    store = RunStore(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_run_store] = lambda: store
    client = TestClient(app)
    try:
        response = client.post("/api/llm/test")
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "mock"
        assert payload["success"] is False
        assert "missing" in payload["message"].lower()
    finally:
        app.dependency_overrides.clear()


def test_llm_test_reports_real_connection_success(tmp_path, monkeypatch):
    settings = Settings(USE_MOCK_LLM=False, OPENAI_API_KEY="test-key", RUNS_DIR=tmp_path)
    store = RunStore(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_run_store] = lambda: store

    def fake_generate_json(self, _system_prompt, _user_payload):
        assert self.mock is False
        return {"ok": True}

    monkeypatch.setattr(LlmClient, "generate_json", fake_generate_json)
    client = TestClient(app)
    try:
        response = client.post("/api/llm/test")
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "real"
        assert payload["success"] is True
        assert payload["api_key_configured"] is True
    finally:
        app.dependency_overrides.clear()


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


def test_intake_generates_chapter_reviews_without_plan(tmp_path):
    client, store = _client_with_store(tmp_path)
    try:
        response = client.post("/api/runs/intake", data={"text": SAMPLE_TEXT})
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        manifest = store.read_manifest(run_id)
        assert manifest.status == RunStatus.awaiting_chapter_review
        assert "chapter_cards.json" in manifest.artifacts
        assert "chapter_reviews.json" in manifest.artifacts
        assert "adaptation_plan.json" not in manifest.artifacts

        reviews = client.get(f"/api/runs/{run_id}/chapter-reviews")
        assert reviews.status_code == 200
        payload = reviews.json()
        assert len(payload["items"]) == 3
        assert payload["items"][0]["review"]["status"] == "ready"
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

        blocked = client.post(f"/api/runs/{run_id}/build-plan")
        assert blocked.status_code == 409

        approve = client.post(f"/api/runs/{run_id}/chapter-cards/approve-all")
        assert approve.status_code == 200
        assert all(
            item["review"]["status"] == "approved"
            for item in approve.json()["items"]
        )

        build = client.post(f"/api/runs/{run_id}/build-plan")
        assert build.status_code == 200
        assert store.read_manifest(run_id).status == RunStatus.planned

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
        assert manifest.status == RunStatus.awaiting_script_review
        assert "chapter_script_cards.json" in manifest.artifacts
        assert "script.yaml" not in manifest.artifacts

        script_reviews = client.get(f"/api/runs/{run_id}/chapter-script-reviews")
        assert script_reviews.status_code == 200
        assert len(script_reviews.json()["items"]) == 3

        approve_scripts = client.post(f"/api/runs/{run_id}/chapter-script-cards/approve-all")
        assert approve_scripts.status_code == 200
        assert all(
            item["review"]["status"] == "approved"
            for item in approve_scripts.json()["items"]
        )

        merge = client.post(f"/api/runs/{run_id}/continuity-merge")
        assert merge.status_code == 200
        manifest = store.read_manifest(run_id)
        script = store.read_json(run_id, "script.json")
        assert manifest.status == RunStatus.awaiting_final_review
        assert script["adaptation_profile"]["adaptation_scale"] == "faithful"
        assert "script.yaml" in manifest.artifacts
    finally:
        app.dependency_overrides.clear()


def test_run_list_and_chapter_regenerate_and_chat_stream(tmp_path):
    client, store = _client_with_store(tmp_path)
    try:
        intake = client.post("/api/runs/intake", data={"text": SAMPLE_TEXT})
        run_id = intake.json()["run_id"]

        runs = client.get("/api/runs")
        assert runs.status_code == 200
        assert runs.json()["runs"][0]["run_id"] == run_id

        before = store.read_json(run_id, "chapter_reviews.json")
        regenerate = client.post(f"/api/runs/{run_id}/chapter-cards/ch_001/regenerate")
        assert regenerate.status_code == 200
        after = store.read_json(run_id, "chapter_reviews.json")
        assert before[0]["revision_count"] == 0
        assert after[0]["revision_count"] == 1
        assert after[0]["status"] == "ready"

        stream = client.post(
            f"/api/runs/{run_id}/chapter-cards/ch_001/chat/stream",
            json={"message": "这章我觉得读偏了"},
        )
        assert stream.status_code == 200
        body = stream.text
        assert "visible_thinking" in body
        assert "tool_event" in body
        assert "assistant_delta" in body
        assert "sk-" not in body
        messages = store.read_json(run_id, "chapter_chat_messages.json")
        assert len(messages) >= 2
    finally:
        app.dependency_overrides.clear()


def test_chapter_script_chat_and_final_feedback_stream(tmp_path):
    client, store = _client_with_store(tmp_path)
    try:
        intake = client.post("/api/runs/intake", data={"text": SAMPLE_TEXT})
        run_id = intake.json()["run_id"]
        client.post(f"/api/runs/{run_id}/chapter-cards/approve-all")
        client.post(f"/api/runs/{run_id}/build-plan")
        client.post(f"/api/runs/{run_id}/generate", json={"controls": {}})

        stream = client.post(
            f"/api/runs/{run_id}/chapter-script-cards/ch_001/chat/stream",
            json={"message": "这章对白太解释"},
        )
        assert stream.status_code == 200
        assert "assistant_delta" in stream.text
        assert "sk-" not in stream.text
        assert len(store.read_json(run_id, "chapter_script_feedback.json")) >= 1

        client.post(f"/api/runs/{run_id}/chapter-script-cards/approve-all")
        client.post(f"/api/runs/{run_id}/continuity-merge")
        feedback_stream = client.post(
            f"/api/runs/{run_id}/final-feedback/chat/stream",
            json={
                "category": "script_point",
                "complaint": "第三章对白太解释",
                "desired_change": "减少解释，加强动作",
            },
        )
        assert feedback_stream.status_code == 200
        body = feedback_stream.text
        assert "final_feedback" in body
        assert "assistant_delta" in body
        assert "sk-" not in body
        assert len(store.read_json(run_id, "final_feedback_chat_messages.json")) >= 2
    finally:
        app.dependency_overrides.clear()


def test_final_feedback_apply_requires_author_confirmation_and_final_confirm(tmp_path):
    client, store = _client_with_store(tmp_path)
    try:
        intake = client.post("/api/runs/intake", data={"text": SAMPLE_TEXT})
        run_id = intake.json()["run_id"]
        client.post(f"/api/runs/{run_id}/chapter-cards/approve-all")
        client.post(f"/api/runs/{run_id}/build-plan")
        client.post(f"/api/runs/{run_id}/generate", json={"controls": {}})
        blocked_before_final = client.post(
            f"/api/runs/{run_id}/final-feedback",
            json={
                "category": "continuity",
                "complaint": "还没生成最终稿就不该返修",
                "desired_change": "等待最终稿",
            },
        )
        assert blocked_before_final.status_code == 409
        client.post(f"/api/runs/{run_id}/chapter-script-cards/approve-all")
        client.post(f"/api/runs/{run_id}/continuity-merge")
        assert store.read_manifest(run_id).status == RunStatus.awaiting_final_review

        before_reviews = store.read_json(run_id, "chapter_script_reviews.json")
        feedback_response = client.post(
            f"/api/runs/{run_id}/final-feedback",
            json={
                "category": "script_point",
                "complaint": "第三章对白太解释",
                "desired_change": "减少解释，加强动作和停顿",
            },
        )
        assert feedback_response.status_code == 200
        assert feedback_response.json()["suggested_chapter_id"] == "ch_003"
        feedback_id = feedback_response.json()["feedback"]["id"]

        apply_without_target = client.post(
            f"/api/runs/{run_id}/final-feedback/{feedback_id}/apply",
            json={"confirmed_chapter_id": None},
        )
        assert apply_without_target.status_code == 409

        apply_missing_target = client.post(
            f"/api/runs/{run_id}/final-feedback/{feedback_id}/apply",
            json={"confirmed_chapter_id": "ch_999"},
        )
        assert apply_missing_target.status_code == 409

        apply = client.post(
            f"/api/runs/{run_id}/final-feedback/{feedback_id}/apply",
            json={"confirmed_chapter_id": "ch_003"},
        )
        assert apply.status_code == 200
        manifest = store.read_manifest(run_id)
        after_reviews = store.read_json(run_id, "chapter_script_reviews.json")
        assert manifest.status == RunStatus.awaiting_script_review
        assert after_reviews[0]["revision_count"] == before_reviews[0]["revision_count"]
        assert after_reviews[1]["revision_count"] == before_reviews[1]["revision_count"]
        assert after_reviews[2]["revision_count"] == before_reviews[2]["revision_count"] + 1
        assert after_reviews[2]["status"] == "ready"
        assert "script.yaml" not in manifest.artifacts

        client.post(f"/api/runs/{run_id}/chapter-script-cards/ch_003/approve")
        client.post(f"/api/runs/{run_id}/continuity-merge")
        confirm = client.post(f"/api/runs/{run_id}/final-confirm")
        assert confirm.status_code == 200
        assert confirm.json()["status"] == "succeeded"

        blocked_after_confirm = client.post(
            f"/api/runs/{run_id}/final-feedback",
            json={
                "category": "continuity",
                "complaint": "确认完成后不应该再回退",
                "desired_change": "重新合成",
            },
        )
        assert blocked_after_confirm.status_code == 409
    finally:
        app.dependency_overrides.clear()
