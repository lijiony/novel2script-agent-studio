from app.core.config import Settings
from app.domain.schemas import PlannerOutput, ReaderOutput, RunStatus
from app.graph.workflow import AdaptationWorkflow
from app.services.run_store import RunStore


def test_mock_workflow_generates_artifacts(tmp_path):
    sample = """第一章 开始
林夏收到第一封信。

第二章 剧院
林夏遇到周砚。

第三章 台词
林夏找到地址。
"""
    settings = Settings(USE_MOCK_LLM=True, RUNS_DIR=tmp_path)
    store = RunStore(tmp_path)
    manifest = store.create_run(sample)
    workflow = AdaptationWorkflow(settings, store)

    workflow.run(manifest.run_id)

    final_manifest = store.read_manifest(manifest.run_id)
    assert final_manifest.status == RunStatus.succeeded
    ReaderOutput.model_validate(store.read_json(manifest.run_id, "reader_output.json"))
    PlannerOutput.model_validate(store.read_json(manifest.run_id, "planner_output.json"))
    assert "script.json" in final_manifest.artifacts
    assert "script.yaml" in final_manifest.artifacts
    assert "adaptation_report.md" in final_manifest.artifacts


def test_workflow_falls_back_to_mock_without_api_key(tmp_path):
    sample = """第一章 开始
林夏收到第一封信。

第二章 剧院
林夏遇到周砚。

第三章 台词
林夏找到地址。
"""
    settings = Settings(USE_MOCK_LLM=False, OPENAI_API_KEY=None, RUNS_DIR=tmp_path)
    store = RunStore(tmp_path)
    manifest = store.create_run(sample)
    workflow = AdaptationWorkflow(settings, store)

    workflow.run(manifest.run_id)

    final_manifest = store.read_manifest(manifest.run_id)
    assert final_manifest.status == RunStatus.succeeded
    assert "script.yaml" in final_manifest.artifacts


def test_workflow_fails_when_repair_cannot_produce_valid_script(tmp_path):
    sample = """第一章 开始
林夏收到第一封信。

第二章 剧院
林夏遇到周砚。

第三章 台词
林夏找到地址。
"""
    settings = Settings(USE_MOCK_LLM=True, RUNS_DIR=tmp_path)
    store = RunStore(tmp_path)
    manifest = store.create_run(sample)
    workflow = AdaptationWorkflow(settings, store)
    original_mock_script = workflow._mock_script

    def invalid_semantic_script(chapters, planner_output):
        script = original_mock_script(chapters, planner_output)
        script["scenes"] = script["scenes"][:1]
        return script

    workflow._mock_script = invalid_semantic_script  # type: ignore[method-assign]

    workflow.run(manifest.run_id)

    final_manifest = store.read_manifest(manifest.run_id)
    assert final_manifest.status == RunStatus.failed_validation
    assert "script.yaml" not in final_manifest.artifacts
    validate_stage = next(stage for stage in final_manifest.stages if stage.name == "validate_schema")
    assert validate_stage.status == "failed"
