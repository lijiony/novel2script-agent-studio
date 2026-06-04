from typing import Any
from langgraph.graph import END, StateGraph

from app.core.config import Settings
from app.domain.chapter_parser import ChapterParseError, parse_chapters
from app.domain.schemas import (
    Chapter,
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


class AdaptationWorkflow:
    def __init__(self, settings: Settings, store: RunStore):
        self.settings = settings
        self.store = store
        self.llm = LlmClient(settings)
        self.graph = self._build_graph()

    def run(self, run_id: str) -> None:
        try:
            input_text = self.store.read_input(run_id)
            self.graph.invoke({"run_id": run_id, "input_text": input_text})
            self.store.succeed(run_id)
        except ChapterParseError as exc:
            self.store.fail(run_id, RunStatus.failed_validation, str(exc))
        except Exception as exc:  # pragma: no cover - integration guard
            self.store.fail(run_id, RunStatus.failed_internal, str(exc))

    def _build_graph(self):
        builder = StateGraph(WorkflowState)
        builder.add_node("validate_input", self._validate_input)
        builder.add_node("parse_chapters", self._parse_chapters)
        builder.add_node("extract_story_facts", self._extract_story_facts)
        builder.add_node("plan_scenes", self._plan_scenes)
        builder.add_node("generate_script_json", self._generate_script_json)
        builder.add_node("validate_schema", self._validate_schema)
        builder.add_node("repair_once_if_needed", self._repair_once_if_needed)
        builder.add_node("export_yaml", self._export_yaml)
        builder.add_node("generate_report", self._generate_report)

        builder.set_entry_point("validate_input")
        builder.add_edge("validate_input", "parse_chapters")
        builder.add_edge("parse_chapters", "extract_story_facts")
        builder.add_edge("extract_story_facts", "plan_scenes")
        builder.add_edge("plan_scenes", "generate_script_json")
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
            reader_output = self._mock_reader_output(chapters)
        else:
            reader_output = self._remote_reader_output(chapters)
        self.store.write_json(state["run_id"], "reader_output.json", reader_output)
        self._finish_stage(state, "extract_story_facts", "Story facts extracted.")
        return {**state, "reader_output": reader_output}

    def _plan_scenes(self, state: WorkflowState) -> WorkflowState:
        self._start_stage(state, "plan_scenes")
        chapters = [Chapter.model_validate(item) for item in state["chapters"]]
        if self.llm.mock:
            planner_output = self._mock_planner_output(chapters)
        else:
            planner_output = self._remote_planner_output(state["reader_output"], chapters)
        self.store.write_json(state["run_id"], "planner_output.json", planner_output)
        self._finish_stage(state, "plan_scenes", "Scene plan created.")
        return {**state, "planner_output": planner_output}

    def _generate_script_json(self, state: WorkflowState) -> WorkflowState:
        self._start_stage(state, "generate_script_json")
        chapters = [Chapter.model_validate(item) for item in state["chapters"]]
        if self.llm.mock:
            payload = self._mock_script(chapters, state["planner_output"])
        else:
            payload = self._remote_script(state["reader_output"], state["planner_output"])
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
        for index, chapter in enumerate(chapters[:5], start=1):
            scenes.append(
                {
                    "id": f"sc_{index:03d}",
                    "title": chapter.title.replace("章", "幕", 1),
                    "source_chapters": [chapter.index],
                    "dramatic_purpose": "Turn chapter prose into a playable dramatic beat.",
                    "key_events": [chapter.text[:100]],
                }
            )
        return {"scenes": scenes}

    def _mock_script(self, chapters: list[Chapter], planner_output: dict[str, Any]) -> dict[str, Any]:
        scenes = []
        for scene_plan in planner_output["scenes"]:
            chapter_index = scene_plan["source_chapters"][0]
            location_id = "loc_archive" if chapter_index == 1 else "loc_theater"
            characters = ["char_linxia"] if chapter_index == 1 else ["char_linxia", "char_zhouyan"]
            scenes.append(
                {
                    "id": scene_plan["id"],
                    "title": scene_plan["title"],
                    "source_chapters": scene_plan["source_chapters"],
                    "location_id": location_id,
                    "time_of_day": "night",
                    "characters": characters,
                    "purpose": scene_plan["dramatic_purpose"],
                    "actions": [
                        {
                            "text": f"林夏进入场景，线索推动她继续追查。来源章节：{chapter_index}。",
                            "beat": "investigation",
                        }
                    ],
                    "dialogues": [
                        {
                            "speaker_id": "char_linxia",
                            "line": "这条线索不是偶然留下的。",
                            "emotion": "determined",
                        }
                    ],
                    "adaptation_notes": [
                        "Compress prose exposition into visible action and concise dialogue."
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
            "Extract characters, locations, events, and props from the novel chapters as JSON.",
            {"chapters": [chapter.model_dump() for chapter in chapters]},
        )

    def _remote_planner_output(
        self, reader_output: dict[str, Any], chapters: list[Chapter]
    ) -> dict[str, Any]:
        return self.llm.generate_json(
            "Create a concise screenplay scene plan. Return JSON only.",
            {
                "reader_output": reader_output,
                "chapters": [chapter.model_dump() for chapter in chapters],
            },
        )

    def _remote_script(
        self, reader_output: dict[str, Any], planner_output: dict[str, Any]
    ) -> dict[str, Any]:
        return self.llm.generate_json(
            "Generate screenplay JSON matching the provided schema. Return JSON only.",
            {
                "schema": script_json_schema(),
                "reader_output": reader_output,
                "planner_output": planner_output,
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
    lines = [
        "# Adaptation Report",
        "",
        f"- Valid: `{report.valid}`",
        f"- Summary: {report.summary}",
        f"- Repaired once: `{state.get('repaired', False)}`",
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
