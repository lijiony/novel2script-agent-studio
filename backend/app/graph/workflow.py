from typing import Any
from langgraph.graph import END, StateGraph

from app.core.config import Settings
from app.domain.chapter_parser import ChapterParseError, parse_chapters
from app.domain.schemas import (
    AdaptationPlan,
    AdaptationRisk,
    AuthorControls,
    Chapter,
    PlannerOutput,
    ReaderOutput,
    RunStatus,
    ScriptJson,
    StoryFact,
    ValidationReport,
    script_json_schema,
)
from app.domain.validators import validate_script_payload
from app.graph.state import WorkflowState
from app.services.llm_client import LlmClient
from app.services.run_store import RunStore
from app.services.schema_docs import schema_markdown
from app.services.yaml_exporter import export_yaml


class WorkflowValidationError(Exception):
    pass


class AdaptationWorkflow:
    def __init__(self, settings: Settings, store: RunStore):
        self.settings = settings
        self.store = store
        self.llm = LlmClient(settings)
        self.plan_graph = self._build_plan_graph()
        self.generate_graph = self._build_generate_graph()

    def run(self, run_id: str) -> None:
        self.plan(run_id)
        if self.store.read_manifest(run_id).status == RunStatus.planned:
            self.generate(run_id, AuthorControls())

    def plan(self, run_id: str) -> None:
        try:
            input_text = self.store.read_input(run_id)
            self.plan_graph.invoke({"run_id": run_id, "input_text": input_text})
            self.store.planned(run_id)
        except (ChapterParseError, WorkflowValidationError) as exc:
            self.store.fail(run_id, RunStatus.failed_validation, str(exc))
        except Exception as exc:  # pragma: no cover - integration guard
            self.store.fail(run_id, RunStatus.failed_internal, str(exc))

    def generate(self, run_id: str, controls: AuthorControls | dict[str, Any] | None = None) -> None:
        try:
            author_controls = AuthorControls.model_validate(controls or {})
            self.store.write_json(run_id, "author_controls.json", author_controls.model_dump(mode="json"))
            self.store.set_stage(
                run_id,
                "await_author_controls",
                "succeeded",
                message="Author controls accepted.",
                run_status=RunStatus.running,
            )
            state = self._load_generation_state(run_id, author_controls)
            self.generate_graph.invoke(state)
            self.store.succeed(run_id)
        except (ChapterParseError, WorkflowValidationError) as exc:
            self.store.fail(run_id, RunStatus.failed_validation, str(exc))
        except Exception as exc:  # pragma: no cover - integration guard
            self.store.fail(run_id, RunStatus.failed_internal, str(exc))

    def _build_plan_graph(self):
        builder = StateGraph(WorkflowState)
        builder.add_node("validate_input", self._validate_input)
        builder.add_node("parse_chapters", self._parse_chapters)
        builder.add_node("extract_story_facts", self._extract_story_facts)
        builder.add_node("plan_adaptation", self._plan_adaptation)

        builder.set_entry_point("validate_input")
        builder.add_edge("validate_input", "parse_chapters")
        builder.add_edge("parse_chapters", "extract_story_facts")
        builder.add_edge("extract_story_facts", "plan_adaptation")
        builder.add_edge("plan_adaptation", END)
        return builder.compile()

    def _build_generate_graph(self):
        builder = StateGraph(WorkflowState)
        builder.add_node("generate_script_json", self._generate_script_json)
        builder.add_node("validate_schema", self._validate_schema)
        builder.add_node("repair_once_if_needed", self._repair_once_if_needed)
        builder.add_node("export_yaml", self._export_yaml)
        builder.add_node("generate_report", self._generate_report)

        builder.set_entry_point("generate_script_json")
        builder.add_edge("generate_script_json", "validate_schema")
        builder.add_conditional_edges(
            "validate_schema",
            self._should_repair,
            {
                "repair": "repair_once_if_needed",
                "export": "export_yaml",
            },
        )
        builder.add_edge("repair_once_if_needed", "validate_schema")
        builder.add_edge("export_yaml", "generate_report")
        builder.add_edge("generate_report", END)
        return builder.compile()

    def _load_generation_state(
        self, run_id: str, author_controls: AuthorControls
    ) -> WorkflowState:
        try:
            chapters = self.store.read_json(run_id, "chapters.json")
            reader_output = self.store.read_json(run_id, "reader_output.json")
            planner_output = self.store.read_json(run_id, "planner_output.json")
            adaptation_plan = self.store.read_json(run_id, "adaptation_plan.json")
        except Exception as exc:
            raise WorkflowValidationError(
                "Run must complete intake planning before generation."
            ) from exc
        return {
            "run_id": run_id,
            "chapters": chapters,  # type: ignore[typeddict-item]
            "reader_output": reader_output,  # type: ignore[typeddict-item]
            "planner_output": planner_output,  # type: ignore[typeddict-item]
            "adaptation_plan": adaptation_plan,  # type: ignore[typeddict-item]
            "author_controls": author_controls.model_dump(mode="json"),
        }

    def _start_stage(
        self, state: WorkflowState, name: str, run_status: RunStatus = RunStatus.running
    ) -> None:
        self.store.set_stage(state["run_id"], name, "running", run_status=run_status)

    def _finish_stage(self, state: WorkflowState, name: str, message: str | None = None) -> None:
        self.store.set_stage(state["run_id"], name, "succeeded", message=message)

    def _validate_input(self, state: WorkflowState) -> WorkflowState:
        self._start_stage(state, "validate_input")
        if not state["input_text"].strip():
            raise ChapterParseError("Input text is empty.")
        self._finish_stage(state, "validate_input", "Input text accepted.")
        return state

    def _parse_chapters(self, state: WorkflowState) -> WorkflowState:
        self._start_stage(state, "parse_chapters")
        chapters = parse_chapters(state["input_text"], max_chars=self.settings.max_input_chars)
        chapter_payloads = [chapter.model_dump() for chapter in chapters]
        self.store.write_json(state["run_id"], "chapters.json", chapter_payloads)
        self._finish_stage(state, "parse_chapters", f"Detected {len(chapters)} chapters.")
        return {**state, "chapters": chapter_payloads}

    def _extract_story_facts(self, state: WorkflowState) -> WorkflowState:
        self._start_stage(state, "extract_story_facts")
        chapters = [Chapter.model_validate(item) for item in state["chapters"]]
        if self.llm.mock:
            raw_reader_output = self._mock_reader_output(chapters)
        else:
            raw_reader_output = self._remote_reader_output(chapters)
        reader_output = ReaderOutput.model_validate(raw_reader_output).model_dump(mode="json")
        self.store.write_json(state["run_id"], "reader_output.json", reader_output)
        self._finish_stage(state, "extract_story_facts", "Story facts extracted.")
        return {**state, "reader_output": reader_output}

    def _plan_adaptation(self, state: WorkflowState) -> WorkflowState:
        self._start_stage(state, "plan_adaptation")
        chapters = [Chapter.model_validate(item) for item in state["chapters"]]
        if self.llm.mock:
            raw_planner_output = self._mock_planner_output(chapters)
        else:
            raw_planner_output = self._remote_planner_output(state["reader_output"], chapters)
        planner_output = PlannerOutput.model_validate(raw_planner_output).model_dump(mode="json")
        adaptation_plan = self._build_adaptation_plan(chapters, state["reader_output"], planner_output)
        self.store.write_json(state["run_id"], "planner_output.json", planner_output)
        self.store.write_json(state["run_id"], "adaptation_plan.json", adaptation_plan)
        self.store.write_text(
            state["run_id"], "adaptation_plan.md", _plan_markdown(adaptation_plan)
        )
        self._finish_stage(state, "plan_adaptation", "Adaptation plan created.")
        return {**state, "planner_output": planner_output, "adaptation_plan": adaptation_plan}

    def _generate_script_json(self, state: WorkflowState) -> WorkflowState:
        self._start_stage(state, "generate_script_json")
        chapters = [Chapter.model_validate(item) for item in state["chapters"]]
        author_controls = AuthorControls.model_validate(state.get("author_controls") or {})
        adaptation_plan = AdaptationPlan.model_validate(state["adaptation_plan"])
        if self.llm.mock:
            payload = self._mock_script(
                chapters, state["planner_output"], adaptation_plan, author_controls
            )
        else:
            payload = self._remote_script(
                state["reader_output"],
                state["planner_output"],
                adaptation_plan.model_dump(mode="json"),
                author_controls.model_dump(mode="json"),
            )
        script = ScriptJson.model_validate(payload)
        script_payload = script.model_dump(mode="json")
        self.store.write_json(state["run_id"], "script.json", script_payload)
        self.store.write_json(state["run_id"], "schema.json", script_json_schema())
        self.store.write_text(state["run_id"], "schema.md", schema_markdown())
        self._finish_stage(state, "generate_script_json", "Script JSON generated.")
        return {**state, "script_json": script_payload, "repaired": False}

    def _validate_schema(self, state: WorkflowState) -> WorkflowState:
        self._start_stage(state, "validate_schema", RunStatus.validating)
        report = validate_script_payload(state["script_json"])
        report_payload = report.model_dump(mode="json")
        self.store.write_json(state["run_id"], "report.json", report_payload)
        message = report.summary
        if state.get("repaired") and not report.valid:
            self.store.set_stage(state["run_id"], "validate_schema", "failed", message=message)
            raise WorkflowValidationError(
                "Validation still failed after one automatic repair attempt."
            )
        self._finish_stage(state, "validate_schema", message)
        return {**state, "validation_report": report_payload}

    def _repair_once_if_needed(self, state: WorkflowState) -> WorkflowState:
        self._start_stage(state, "repair_once_if_needed", RunStatus.repairing)
        report = ValidationReport.model_validate(state["validation_report"])
        script_payload = dict(state["script_json"])
        if report.valid:
            self._finish_stage(state, "repair_once_if_needed", "No repair needed.")
            return {**state, "repaired": True}

        repaired_payload = self._deterministic_repair(script_payload)
        ScriptJson.model_validate(repaired_payload)
        self.store.write_json(state["run_id"], "script.json", repaired_payload)
        self._finish_stage(state, "repair_once_if_needed", "One repair attempt completed.")
        return {**state, "script_json": repaired_payload, "repaired": True}

    def _export_yaml(self, state: WorkflowState) -> WorkflowState:
        self._start_stage(state, "export_yaml", RunStatus.exporting)
        yaml_text = export_yaml(state["script_json"])
        self.store.write_text(state["run_id"], "script.yaml", yaml_text)
        self._finish_stage(state, "export_yaml", "YAML exported.")
        return {**state, "yaml_text": yaml_text}

    def _generate_report(self, state: WorkflowState) -> WorkflowState:
        self._start_stage(state, "generate_report")
        report = ValidationReport.model_validate(state["validation_report"])
        markdown = _report_markdown(report, state)
        self.store.write_text(state["run_id"], "adaptation_report.md", markdown)
        self._finish_stage(state, "generate_report", "Adaptation report generated.")
        return {**state, "report_markdown": markdown}

    @staticmethod
    def _should_repair(state: WorkflowState) -> str:
        report = ValidationReport.model_validate(state["validation_report"])
        if report.valid:
            return "export"
        if state.get("repaired"):
            return "export"
        return "repair"

    def _mock_reader_output(self, chapters: list[Chapter]) -> dict[str, Any]:
        facts = [
            StoryFact(
                kind="character",
                name="林夏",
                description="A careful archivist following clues left by her missing father.",
                source_chapter=1,
            ),
            StoryFact(
                kind="character",
                name="周砚",
                description="An elderly stage manager who knows the old theater secret.",
                source_chapter=2,
            ),
            StoryFact(
                kind="location",
                name="城南档案馆",
                description="The archive where the first letter is discovered.",
                source_chapter=1,
            ),
            StoryFact(
                kind="location",
                name="旧剧院",
                description="An abandoned theater lit by a single stage lamp.",
                source_chapter=2,
            ),
        ]
        for chapter in chapters:
            facts.append(
                StoryFact(
                    kind="event",
                    name=f"{chapter.title} 的关键事件",
                    description=chapter.text[:120],
                    source_chapter=chapter.index,
                )
            )
        return {"facts": [fact.model_dump() for fact in facts]}

    def _mock_planner_output(self, chapters: list[Chapter]) -> dict[str, Any]:
        scenes = []
        purposes = [
            "Establish the inciting clue and turn atmosphere into a visible discovery.",
            "Introduce the mentor figure and make the hidden past confront the protagonist.",
            "Convert the textual clue into a decisive next-step action beat.",
            "Compress the chapter into a high-pressure turning point.",
            "Resolve the immediate question while opening the next dramatic hook.",
        ]
        conflicts = [
            "林夏想确认信件来源，但信上的旧剧院把父亲失踪重新拉回眼前。",
            "周砚知道真相却不愿全说，林夏必须在信任和怀疑之间逼近答案。",
            "旧剧本给出地址，也证明父亲的失踪不是意外，林夏必须选择是否继续。",
            "线索终于成形，但每个答案都会暴露一个更危险的秘密。",
            "主角得到短暂确认，却必须付出更大的行动代价。",
        ]
        shifts = [
            "从谨慎好奇到被迫行动。",
            "从警惕试探到暂时结盟。",
            "从焦虑困惑到坚定追查。",
            "从被动接收线索到主动改变计划。",
            "从短暂释然到意识到更深危机。",
        ]
        for index, chapter in enumerate(chapters[:5], start=1):
            scenes.append(
                {
                    "id": f"sc_{index:03d}",
                    "title": chapter.title.replace("章", "幕", 1),
                    "source_chapters": [chapter.index],
                    "dramatic_purpose": purposes[index - 1],
                    "key_events": [chapter.text[:100]],
                    "conflict": conflicts[index - 1],
                    "emotional_shift": shifts[index - 1],
                    "source_excerpt": chapter.text[:140],
                }
            )
        return {"scenes": scenes}

    def _build_adaptation_plan(
        self,
        chapters: list[Chapter],
        reader_output: dict[str, Any],
        planner_output: dict[str, Any],
    ) -> dict[str, Any]:
        facts = ReaderOutput.model_validate(reader_output).facts
        planner = PlannerOutput.model_validate(planner_output)
        character_notes = [
            f"{fact.name}: {fact.description}"
            for fact in facts
            if fact.kind == "character"
        ]
        plot_threads = [
            fact.description
            for fact in facts
            if fact.kind in {"event", "prop"}
        ][:5]
        risks = [
            AdaptationRisk(
                severity="warning",
                target="心理描写外化",
                message="原文包含内心判断，需要转换成可拍动作、停顿或对白。",
                suggestion="为每场戏加入可见行动和情绪转折，不只复述背景。",
            ),
            AdaptationRisk(
                severity="info",
                target="章节覆盖",
                message="当前计划为每章至少安排一个场景，便于作者追踪来源。",
                suggestion="如果生成短剧版，可在后续合并相邻低冲突场景。",
            ),
        ]
        plan = AdaptationPlan(
            summary=(
                "建议先做忠实但更具戏剧推动力的短剧版：保留人物关系和线索链，"
                "把心理与氛围转成动作、对白和场景冲突。"
            ),
            chapter_count=len(chapters),
            rationale=[
                "短剧结构适合在 demo 中展示清晰场景目标和节奏压缩。",
                "心理外化能直接回应小说改编为可表演内容的核心难点。",
                "平衡尺度可以保留原著味道，同时允许必要的场景合并和对白改写。",
            ],
            character_notes=character_notes,
            plot_threads=plot_threads,
            scene_plan=planner.scenes,
            risks=risks,
        )
        return plan.model_dump(mode="json")

    def _mock_script(
        self,
        chapters: list[Chapter],
        planner_output: dict[str, Any],
        adaptation_plan: AdaptationPlan,
        controls: AuthorControls,
    ) -> dict[str, Any]:
        scenes = []
        action_texts = [
            "林夏把没有编号的信压在台灯下，翻出父亲旧档案，手指停在同一个剧院名上。",
            "旧剧院的灯忽明忽暗，周砚挡在舞台边，不让林夏靠近后台的铁门。",
            "林夏用铅笔圈出第三幕每句台词的首字，把它们连成城北钟楼的地址。",
            "林夏把零散线索排成时间线，意识到有人一直在引导她走向同一个地点。",
            "林夏收起旧剧本，关掉舞台灯，只留下信封上的地址在黑暗里发白。",
        ]
        dialogue_lines = [
            "这不是馆里的编号，是他留给我的。",
            "你认识我父亲，也知道这盏灯为什么还亮着。",
            "第三幕不是结尾，是路线。",
            "如果这是警告，他为什么要把每一步都写清楚？",
            "我会去钟楼，但我要先知道谁希望我去。",
        ]
        risks = [
            "Opening scene needs tactile investigation beats so it does not rely on narration.",
            "Mentor scene needs blocking and silence to avoid pure exposition.",
            "Clue-solving scene needs visible pattern discovery so the reveal feels playable.",
            "Timeline scene may become static; add pressure or interruption if extended.",
            "Ending beat should preserve suspense instead of over-explaining the next act.",
        ]
        for scene_plan in planner_output["scenes"]:
            chapter_index = scene_plan["source_chapters"][0]
            variant_index = min(chapter_index - 1, len(action_texts) - 1)
            location_id = "loc_archive" if chapter_index == 1 else "loc_theater"
            characters = ["char_linxia"] if chapter_index == 1 else ["char_linxia", "char_zhouyan"]
            scenes.append(
                {
                    "id": scene_plan["id"],
                    "title": scene_plan["title"],
                    "source_chapters": scene_plan["source_chapters"],
                    "source_excerpt": scene_plan.get("source_excerpt") or scene_plan["key_events"][0],
                    "location_id": location_id,
                    "time_of_day": "night",
                    "characters": characters,
                    "purpose": scene_plan["dramatic_purpose"],
                    "scene_purpose": scene_plan["dramatic_purpose"],
                    "conflict": scene_plan.get("conflict")
                    or "A clue demands action while the character fears what it reveals.",
                    "emotional_shift": scene_plan.get("emotional_shift")
                    or "From hesitation to decision.",
                    "production_risk": risks[variant_index],
                    "format_type": controls.format_type.value,
                    "actions": [
                        {
                            "text": action_texts[variant_index],
                            "beat": "investigation",
                            "origin": "ai_adapted",
                        }
                    ],
                    "dialogues": [
                        {
                            "speaker_id": "char_linxia",
                            "line": dialogue_lines[variant_index],
                            "emotion": "determined",
                            "origin": "ai_adapted",
                        }
                    ],
                    "ai_added_content": [
                        "Add a playable beat that externalizes the chapter's inner suspicion."
                    ],
                    "revision_suggestions": [
                        "Strengthen the opposing force if the scene feels too explanatory."
                    ],
                    "adaptation_notes": [
                        "Compress prose exposition into visible action and concise dialogue.",
                        f"Author style focus: {controls.style_focus.value}.",
                    ],
                }
            )
        return {
            "metadata": {
                "title": "雨巷里的来信",
                "source_chapter_count": len(chapters),
                "language": "zh-CN",
                "genre": "mystery drama",
                "logline": "A young archivist follows hidden letters through an abandoned theater to uncover why her father vanished.",
            },
            "adaptation_profile": controls.model_dump(mode="json"),
            "adaptation_strategy": [
                adaptation_plan.summary,
                "Track source chapters and excerpts so the author can audit what changed.",
                "Label AI additions separately from adapted source material.",
            ],
            "characters": [
                {
                    "id": "char_linxia",
                    "name": "林夏",
                    "role": "protagonist",
                    "description": "A careful young archivist who decides to continue her father's unfinished investigation.",
                    "first_appearance_chapter": 1,
                },
                {
                    "id": "char_zhouyan",
                    "name": "周砚",
                    "role": "mentor",
                    "description": "A former stage manager who reveals the old theater's hidden secret.",
                    "first_appearance_chapter": 2,
                },
            ],
            "locations": [
                {
                    "id": "loc_archive",
                    "name": "城南档案馆",
                    "description": "An old archive near a rain-soaked alley.",
                },
                {
                    "id": "loc_theater",
                    "name": "旧剧院",
                    "description": "A closed theater where one stage lamp still burns.",
                },
            ],
            "props": [
                {
                    "id": "prop_letter",
                    "name": "没有编号的信",
                    "description": "A mysterious letter written in the protagonist's father's hand.",
                },
                {
                    "id": "prop_script",
                    "name": "旧剧本",
                    "description": "A theater script whose third act hides an address.",
                },
            ],
            "scenes": scenes,
            "adaptation_notes": [
                "Keep the mystery clue chain visible from chapter to chapter.",
                "Use scene purposes to make the YAML draft easy to continue polishing.",
            ],
        }

    def _remote_reader_output(self, chapters: list[Chapter]) -> dict[str, Any]:
        return self.llm.generate_json(
            "Extract characters, locations, events, and props. Return JSON only matching the provided ReaderOutput schema.",
            {
                "schema": ReaderOutput.model_json_schema(),
                "chapters": [chapter.model_dump() for chapter in chapters],
            },
        )

    def _remote_planner_output(
        self, reader_output: dict[str, Any], chapters: list[Chapter]
    ) -> dict[str, Any]:
        return self.llm.generate_json(
            "Create a concise screenplay scene plan with scene purpose, conflict, emotional shift, and source excerpt. Return JSON only matching the provided PlannerOutput schema.",
            {
                "schema": PlannerOutput.model_json_schema(),
                "reader_output": reader_output,
                "chapters": [chapter.model_dump() for chapter in chapters],
            },
        )

    def _remote_script(
        self,
        reader_output: dict[str, Any],
        planner_output: dict[str, Any],
        adaptation_plan: dict[str, Any],
        author_controls: dict[str, Any],
    ) -> dict[str, Any]:
        return self.llm.generate_json(
            "Generate screenplay JSON matching the provided schema. Return JSON only.",
            {
                "schema": script_json_schema(),
                "reader_output": reader_output,
                "planner_output": planner_output,
                "adaptation_plan": adaptation_plan,
                "author_controls": author_controls,
            },
        )

    @staticmethod
    def _deterministic_repair(script_payload: dict[str, Any]) -> dict[str, Any]:
        characters = script_payload.get("characters", [])
        locations = script_payload.get("locations", [])
        fallback_character = characters[0]["id"] if characters else "char_unknown"
        fallback_location = locations[0]["id"] if locations else "loc_unknown"
        if not characters:
            script_payload["characters"] = [
                {
                    "id": fallback_character,
                    "name": "Unknown Character",
                    "role": "supporting",
                    "description": "Fallback character inserted during repair.",
                    "first_appearance_chapter": 1,
                }
            ]
        if not locations:
            script_payload["locations"] = [
                {
                    "id": fallback_location,
                    "name": "Unknown Location",
                    "description": "Fallback location inserted during repair.",
                }
            ]
        for scene in script_payload.get("scenes", []):
            scene.setdefault("characters", [fallback_character])
            scene["characters"] = [
                char_id
                for char_id in scene["characters"]
                if char_id in {character["id"] for character in script_payload["characters"]}
            ] or [fallback_character]
            if scene.get("location_id") not in {
                location["id"] for location in script_payload["locations"]
            }:
                scene["location_id"] = fallback_location
            if not scene.get("actions") and not scene.get("dialogues"):
                scene["actions"] = [{"text": "Repair inserted a minimal action beat.", "beat": "repair"}]
        return script_payload


def _report_markdown(report: ValidationReport, state: WorkflowState) -> str:
    controls = AuthorControls.model_validate(state.get("author_controls") or {})
    plan = AdaptationPlan.model_validate(state.get("adaptation_plan") or {})
    lines = [
        "# Adaptation Report",
        "",
        f"- Valid: `{report.valid}`",
        f"- Summary: {report.summary}",
        f"- Repaired once: `{state.get('repaired', False)}`",
        f"- Format type: `{controls.format_type.value}`",
        f"- Adaptation scale: `{controls.adaptation_scale.value}`",
        f"- Style focus: `{controls.style_focus.value}`",
        "",
        "## Strategy",
        "",
        plan.summary,
        "",
        "## Issues",
        "",
    ]
    if not report.issues:
        lines.append("No validation issues were found.")
    else:
        for issue in report.issues:
            lines.append(f"- **{issue.severity.value}** `{issue.path}`: {issue.message}")
            if issue.suggestion:
                lines.append(f"  Suggestion: {issue.suggestion}")
    return "\n".join(lines) + "\n"


def _plan_markdown(plan_payload: dict[str, Any]) -> str:
    plan = AdaptationPlan.model_validate(plan_payload)
    lines = [
        "# Adaptation Plan",
        "",
        f"- Chapters: `{plan.chapter_count}`",
        f"- Recommended format: `{plan.recommended_format_type.value}`",
        f"- Recommended style: `{plan.recommended_style_focus.value}`",
        f"- Recommended scale: `{plan.recommended_adaptation_scale.value}`",
        "",
        "## Summary",
        "",
        plan.summary,
        "",
        "## Rationale",
        "",
    ]
    lines.extend(f"- {item}" for item in plan.rationale)
    lines.extend(["", "## Character Notes", ""])
    lines.extend(f"- {item}" for item in plan.character_notes)
    lines.extend(["", "## Scene Plan", ""])
    for scene in plan.scene_plan:
        lines.append(
            f"- `{scene.id}` {scene.title}: {scene.dramatic_purpose} "
            f"(chapters: {', '.join(str(item) for item in scene.source_chapters)})"
        )
        if scene.conflict:
            lines.append(f"  Conflict: {scene.conflict}")
        if scene.emotional_shift:
            lines.append(f"  Emotional shift: {scene.emotional_shift}")
    lines.extend(["", "## Risks", ""])
    for risk in plan.risks:
        lines.append(f"- **{risk.severity}** {risk.target}: {risk.message}")
        lines.append(f"  Suggestion: {risk.suggestion}")
    return "\n".join(lines) + "\n"
