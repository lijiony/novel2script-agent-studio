from app.core.config import Settings
from app.domain.schemas import (
    AdaptationPlan,
    AuthorControls,
    ChapterCard,
    ChapterScriptCard,
    PlannerOutput,
    ReaderOutput,
    RunStatus,
    ScriptFormat,
    StyleFocus,
    StoryBible,
)
from app.graph.workflow import AdaptationWorkflow, _chapter_number_markers
from app.services.run_store import RunStore


def _complete_author_review_flow(
    workflow: AdaptationWorkflow,
    run_id: str,
    controls: AuthorControls | None = None,
) -> None:
    workflow.intake(run_id)
    workflow.approve_all_chapters(run_id)
    workflow.build_plan(run_id)
    workflow.generate(run_id, controls or AuthorControls())
    workflow.approve_all_chapter_scripts(run_id)
    workflow.continuity_merge(run_id)


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

    _complete_author_review_flow(workflow, manifest.run_id)

    final_manifest = store.read_manifest(manifest.run_id)
    assert final_manifest.status == RunStatus.awaiting_final_review
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
    assert "chapter_script_cards.json" in final_manifest.artifacts
    assert "chapter_script_reviews.json" in final_manifest.artifacts
    assert "continuity_report.md" in final_manifest.artifacts
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

    workflow.intake(manifest.run_id)

    review_manifest = store.read_manifest(manifest.run_id)
    assert review_manifest.status == RunStatus.awaiting_chapter_review
    reviews = store.read_json(manifest.run_id, "chapter_reviews.json")
    assert all(review["status"] == "ready" for review in reviews)

    workflow.approve_all_chapters(manifest.run_id)
    workflow.build_plan(manifest.run_id)

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

    script_review_manifest = store.read_manifest(manifest.run_id)
    assert script_review_manifest.status == RunStatus.awaiting_script_review
    assert "chapter_script_cards.json" in script_review_manifest.artifacts
    assert "script.yaml" not in script_review_manifest.artifacts

    workflow.approve_all_chapter_scripts(manifest.run_id)
    workflow.continuity_merge(manifest.run_id)

    final_manifest = store.read_manifest(manifest.run_id)
    script = store.read_json(manifest.run_id, "script.json")
    assert final_manifest.status == RunStatus.awaiting_final_review
    assert script["adaptation_profile"]["format_type"] == "short_drama"
    assert script["adaptation_profile"]["style_focus"] == "psychological"
    assert script["scenes"][0]["format_type"] == "short_drama"
    assert script["scenes"][0]["source_function"]
    assert script["scenes"][0]["adaptation_reason"]
    assert script["scenes"][0]["performance_notes"]
    assert script["scenes"][0]["actions"][0]["origin"] == "ai_adapted"
    assert "continuity_report.md" in final_manifest.artifacts


def test_final_feedback_can_rerun_continuity_or_single_chapter(tmp_path):
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

    workflow.intake(manifest.run_id)
    workflow.approve_all_chapters(manifest.run_id)
    workflow.build_plan(manifest.run_id)
    workflow.generate(manifest.run_id, AuthorControls())
    workflow.approve_all_chapter_scripts(manifest.run_id)
    workflow.continuity_merge(manifest.run_id)

    before_reviews = store.read_json(manifest.run_id, "chapter_script_reviews.json")
    continuity_feedback = workflow.create_final_feedback(
        manifest.run_id,
        "continuity",
        "第二章和第三章之间过渡太突然",
        "增加线索承接",
    )
    workflow.apply_final_feedback(manifest.run_id, continuity_feedback.id)
    after_continuity_reviews = store.read_json(manifest.run_id, "chapter_script_reviews.json")
    assert before_reviews == after_continuity_reviews
    assert store.read_manifest(manifest.run_id).status == RunStatus.awaiting_final_review

    point_feedback = workflow.create_final_feedback(
        manifest.run_id,
        "script_point",
        "第三章对白太解释",
        "减少解释，加强动作",
    )
    assert point_feedback.target_chapter_id == "ch_003"
    workflow.apply_final_feedback(manifest.run_id, point_feedback.id, "ch_003")
    after_point_reviews = store.read_json(manifest.run_id, "chapter_script_reviews.json")
    assert after_point_reviews[0]["revision_count"] == before_reviews[0]["revision_count"]
    assert after_point_reviews[1]["revision_count"] == before_reviews[1]["revision_count"]
    assert after_point_reviews[2]["revision_count"] == before_reviews[2]["revision_count"] + 1
    assert after_point_reviews[2]["status"] == "approved"
    assert store.read_manifest(manifest.run_id).status == RunStatus.awaiting_final_review
    assert "script.yaml" in store.read_manifest(manifest.run_id).artifacts

    mixed_feedback = workflow.create_final_feedback(
        manifest.run_id,
        "chapter_and_continuity",
        "第三章对白太解释，第二章第三章之间过渡也不顺",
        "先改第三章，再让章节过渡自然一些",
    )
    assert mixed_feedback.target_type == "chapter_and_continuity"
    assert mixed_feedback.target_chapter_id in {"ch_002", "ch_003"}
    workflow.apply_final_feedback(manifest.run_id, mixed_feedback.id, mixed_feedback.target_chapter_id)
    assert store.read_manifest(manifest.run_id).status == RunStatus.awaiting_final_review
    assert "script.yaml" in store.read_manifest(manifest.run_id).artifacts


def test_chinese_two_digit_chapter_markers_are_supported():
    markers = _chapter_number_markers(11)

    assert "第十一章" in markers
    assert "第 11 章" in markers


def test_mock_workflow_handles_many_chapters_without_chunking(tmp_path):
    sample = "\n\n".join(
        f"第{index}章 长篇章节{index}\n林夏在第{index}章继续追查父亲留下的线索，旧剧院和城北钟楼反复出现。"
        for index in range(1, 51)
    )
    settings = Settings(USE_MOCK_LLM=True, RUNS_DIR=tmp_path, MAX_INPUT_CHARS=200000)
    store = RunStore(tmp_path)
    manifest = store.create_run(sample)
    workflow = AdaptationWorkflow(settings, store)

    workflow.intake(manifest.run_id)
    workflow.approve_all_chapters(manifest.run_id)
    workflow.build_plan(manifest.run_id)

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


def test_author_generation_scope_controls_script_cards(tmp_path):
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

    workflow.intake(manifest.run_id)
    workflow.approve_all_chapters(manifest.run_id)
    workflow.build_plan(manifest.run_id)

    story_bible = store.read_json(manifest.run_id, "story_bible.json")
    story_bible["recommended_generation_scope"] = [1, 3]
    store.write_json(manifest.run_id, "story_bible.json", story_bible)

    workflow.generate(manifest.run_id, AuthorControls(generation_scope=[1, 3]))

    script_cards = store.read_json(manifest.run_id, "chapter_script_cards.json")
    assert [card["chapter_id"] for card in script_cards] == ["ch_001", "ch_003"]


def test_script_reference_normalization_accepts_real_model_aliases(tmp_path):
    settings = Settings(USE_MOCK_LLM=True, RUNS_DIR=tmp_path)
    store = RunStore(tmp_path)
    workflow = AdaptationWorkflow(settings, store)

    scenes, characters, locations = workflow._normalize_script_references(  # noqa: SLF001
        [
            {
                "source_chapters": [2],
                "location_id": "城北钟楼",
                "characters": ["林夏", "周砚"],
                "dialogues": [
                    {"speaker_id": "char_zhou_yan", "line": "别问了。"},
                    {"speaker_id": "char_mother", "line": "别再查了。"},
                ],
            }
        ]
    )

    assert scenes[0]["location_id"] == "loc_clocktower"
    assert scenes[0]["characters"] == ["char_linxia", "char_zhouyan", "char_mother"]
    assert scenes[0]["dialogues"][0]["speaker_id"] == "char_zhouyan"
    assert {character["id"] for character in characters} >= {
        "char_linxia",
        "char_zhouyan",
        "char_mother",
    }
    assert {location["id"] for location in locations} >= {"loc_clocktower"}


def test_chapter_script_payload_normalizes_real_model_ids_before_validation(tmp_path):
    settings = Settings(USE_MOCK_LLM=True, RUNS_DIR=tmp_path)
    store = RunStore(tmp_path)
    workflow = AdaptationWorkflow(settings, store)

    payload = {
        "chapter_id": "ch_001",
        "chapter_index": 1,
        "title": "线索显影",
        "summary": "林夏和周砚把旧剧院线索转成可表演动作。",
        "scenes": [
            {
                "id": "scene_1",
                "title": "旧剧院后台",
                "source_chapters": [1],
                "source_excerpt": "林夏发现父亲留下的线索。",
                "source_function": "发现线索，推动追查。",
                "location_id": "loc_旧剧院",
                "time_of_day": "night",
                "characters": ["char_林夏"],
                "purpose": "让主角做出继续追查的决定。",
                "scene_purpose": "把心理判断外化为行动。",
                "conflict": "线索真假不明，周砚不愿说明。",
                "emotional_shift": "从怀疑到决定追查。",
                "production_risk": "避免只用台词解释线索。",
                "actions": [{"text": "林夏把旧门票压在灯下。"}],
                "dialogues": [
                    {"speaker_id": "char_林夏", "line": "我要知道父亲当年去了哪里。"},
                    {"speaker_id": "char_周砚", "line": "那你就别只看票面。"},
                ],
            }
        ],
        "opening_bridge": "从第一条线索开始。",
        "ending_hook": "旧剧院钟声响起。",
        "continuity_links": ["后续章节继续追查父亲失踪。"],
        "absorbed_feedback": [],
        "revision_notes": [],
        "format_type": "short_drama",
    }

    normalized = workflow._normalize_chapter_script_card_payload(payload)  # noqa: SLF001
    card = ChapterScriptCard.model_validate(normalized)

    assert card.scenes[0].id == "sc_001"
    assert card.scenes[0].location_id == "loc_theater"
    assert card.scenes[0].characters == ["char_linxia", "char_zhouyan"]
    assert card.scenes[0].dialogues[0].speaker_id == "char_linxia"
    assert card.scenes[0].dialogues[1].speaker_id == "char_zhouyan"


def test_planner_output_payload_stringifies_structured_excerpts(tmp_path):
    settings = Settings(USE_MOCK_LLM=True, RUNS_DIR=tmp_path)
    store = RunStore(tmp_path)
    workflow = AdaptationWorkflow(settings, store)

    normalized = workflow._normalize_planner_output_payload(  # noqa: SLF001
        {
            "scenes": [
                {
                    "id": "scene_1",
                    "title": {"text": "旧剧院线索显影"},
                    "source_chapters": [1],
                    "dramatic_purpose": {"summary": "让林夏决定继续追查。"},
                    "key_events": [{"summary": "发现父亲留下的线索"}],
                    "source_excerpt": {
                        "quote": "林夏在旧剧院发现父亲留下的线索。",
                        "reason": "这是本章核心事件与悬念。",
                    },
                }
            ]
        }
    )

    planner_output = PlannerOutput.model_validate(normalized)

    assert planner_output.scenes[0].id == "sc_001"
    assert planner_output.scenes[0].title == "旧剧院线索显影"
    assert planner_output.scenes[0].dramatic_purpose == "让林夏决定继续追查。"
    assert planner_output.scenes[0].key_events == ["发现父亲留下的线索"]
    assert planner_output.scenes[0].source_excerpt == (
        "林夏在旧剧院发现父亲留下的线索。；这是本章核心事件与悬念。"
    )


def test_regenerate_chapter_only_updates_target_card(tmp_path):
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

    workflow.intake(manifest.run_id)
    before = store.read_json(manifest.run_id, "chapter_cards.json")
    workflow.regenerate_chapter(manifest.run_id, "ch_002")
    after = store.read_json(manifest.run_id, "chapter_cards.json")
    reviews = store.read_json(manifest.run_id, "chapter_reviews.json")

    assert before[0] == after[0]
    assert before[2] == after[2]
    assert reviews[1]["revision_count"] == 1
    assert reviews[1]["status"] == "ready"


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

    _complete_author_review_flow(workflow, manifest.run_id)

    final_manifest = store.read_manifest(manifest.run_id)
    assert final_manifest.status == RunStatus.awaiting_final_review
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

    workflow.intake(manifest.run_id)

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

    original_merge = workflow._script_from_chapter_script_cards

    def invalid_semantic_script(chapters, script_cards, adaptation_plan, controls, feedback):
        script = original_merge(chapters, script_cards, adaptation_plan, controls, feedback)
        script["scenes"] = script["scenes"][:1]
        return script

    workflow._script_from_chapter_script_cards = invalid_semantic_script  # type: ignore[method-assign]

    _complete_author_review_flow(workflow, manifest.run_id)

    final_manifest = store.read_manifest(manifest.run_id)
    assert final_manifest.status == RunStatus.failed_validation
    assert "script.yaml" not in final_manifest.artifacts
    validate_stage = next(stage for stage in final_manifest.stages if stage.name == "validate_schema")
    assert validate_stage.status == "failed"
