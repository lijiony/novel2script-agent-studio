from app.core.config import Settings
from app.domain.schemas import (
    AdaptationPlan,
    AuthorControls,
    ChapterCard,
    PlannerOutput,
    ReaderOutput,
    RunStatus,
    ScriptFormat,
    StyleFocus,
    StoryBible,
)
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
    chapter_cards = store.read_json(manifest.run_id, "chapter_cards.json")
    assert len(chapter_cards) == 3
    ChapterCard.model_validate(chapter_cards[0])
    StoryBible.model_validate(store.read_json(manifest.run_id, "story_bible.json"))
    ReaderOutput.model_validate(store.read_json(manifest.run_id, "reader_output.json"))
    planner_output = PlannerOutput.model_validate(store.read_json(manifest.run_id, "planner_output.json"))
    plan = AdaptationPlan.model_validate(store.read_json(manifest.run_id, "adaptation_plan.json"))
    plan_markdown = store.read_text(manifest.run_id, "adaptation_plan.md")
    assert planner_output.scenes[0].source_function
    assert planner_output.scenes[0].adaptation_reason
    assert plan.format_rationale
    assert plan.technical_notes
    assert "为什么推荐这个方向" in plan_markdown
    assert "分章改编理由" in plan_markdown
    assert "长文本处理说明" in plan_markdown
    assert "short_drama" not in plan_markdown
    assert "story_bible.md" in final_manifest.artifacts
    assert "script.json" in final_manifest.artifacts
    assert "script.yaml" in final_manifest.artifacts
    assert "adaptation_report.md" in final_manifest.artifacts


def test_mock_workflow_supports_plan_then_generate(tmp_path):
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

    workflow.plan(manifest.run_id)

    planned_manifest = store.read_manifest(manifest.run_id)
    assert planned_manifest.status == RunStatus.planned
    assert "chapter_cards.json" in planned_manifest.artifacts
    assert "story_bible.json" in planned_manifest.artifacts
    assert "adaptation_plan.json" in planned_manifest.artifacts
    assert "adaptation_plan.md" in planned_manifest.artifacts

    controls = AuthorControls(
        format_type=ScriptFormat.short_drama,
        style_focus=StyleFocus.psychological,
        preserve_items=["保留林夏和周砚的关系"],
        forbidden_changes=["不要改变父亲失踪的核心设定"],
        author_notes="对白要克制，心理活动尽量转成动作。",
    )
    workflow.generate(manifest.run_id, controls)

    final_manifest = store.read_manifest(manifest.run_id)
    script = store.read_json(manifest.run_id, "script.json")
    assert final_manifest.status == RunStatus.succeeded
    assert script["adaptation_profile"]["format_type"] == "short_drama"
    assert script["adaptation_profile"]["style_focus"] == "psychological"
    assert script["scenes"][0]["format_type"] == "short_drama"
    assert script["scenes"][0]["source_function"]
    assert script["scenes"][0]["adaptation_reason"]
    assert script["scenes"][0]["performance_notes"]
    assert script["scenes"][0]["actions"][0]["origin"] == "ai_adapted"


def test_mock_workflow_handles_many_chapters_without_chunking(tmp_path):
    sample = "\n\n".join(
        f"第{index}章 长篇章节{index}\n林夏在第{index}章继续追查父亲留下的线索，旧剧院和城北钟楼反复出现。"
        for index in range(1, 51)
    )
    settings = Settings(USE_MOCK_LLM=True, RUNS_DIR=tmp_path, MAX_INPUT_CHARS=200000)
    store = RunStore(tmp_path)
    manifest = store.create_run(sample)
    workflow = AdaptationWorkflow(settings, store)

    workflow.plan(manifest.run_id)

    planned_manifest = store.read_manifest(manifest.run_id)
    chapter_cards = store.read_json(manifest.run_id, "chapter_cards.json")
    story_bible = StoryBible.model_validate(store.read_json(manifest.run_id, "story_bible.json"))
    plan = AdaptationPlan.model_validate(store.read_json(manifest.run_id, "adaptation_plan.json"))

    assert planned_manifest.status == RunStatus.planned
    assert len(chapter_cards) == 50
    assert story_bible.recommended_generation_scope == [1, 2, 3]
    assert plan.recommended_generation_scope == [1, 2, 3]
    assert plan.technical_notes
    assert plan.scene_plan[0].adaptation_reason


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


def test_real_llm_error_is_reported_as_failed_llm(tmp_path):
    sample = """第一章 开始
林夏收到第一封信。

第二章 剧院
林夏遇到周砚。

第三章 台词
林夏找到地址。
"""
    settings = Settings(USE_MOCK_LLM=False, OPENAI_API_KEY="test-key", RUNS_DIR=tmp_path)
    store = RunStore(tmp_path)
    manifest = store.create_run(sample)
    workflow = AdaptationWorkflow(settings, store)

    def fail_generate_json(_system_prompt, _user_payload):
        raise RuntimeError("provider unavailable")

    workflow.llm.generate_json = fail_generate_json  # type: ignore[method-assign]

    workflow.plan(manifest.run_id)

    final_manifest = store.read_manifest(manifest.run_id)
    assert final_manifest.status == RunStatus.failed_llm
    assert "provider unavailable" in (final_manifest.error or "")


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

    def invalid_semantic_script(chapters, planner_output, adaptation_plan, controls):
        script = original_mock_script(chapters, planner_output, adaptation_plan, controls)
        script["scenes"] = script["scenes"][:1]
        return script

    workflow._mock_script = invalid_semantic_script  # type: ignore[method-assign]

    workflow.run(manifest.run_id)

    final_manifest = store.read_manifest(manifest.run_id)
    assert final_manifest.status == RunStatus.failed_validation
    assert "script.yaml" not in final_manifest.artifacts
    validate_stage = next(stage for stage in final_manifest.stages if stage.name == "validate_schema")
    assert validate_stage.status == "failed"
