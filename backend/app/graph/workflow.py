from typing import Any
from langgraph.graph import END, StateGraph

from app.core.config import Settings
from app.domain.chapter_parser import ChapterParseError, parse_chapters
from app.domain.schemas import (
    AdaptationPlan,
    AdaptationRisk,
    AuthorControls,
    Chapter,
    ChapterCard,
    PlannerOutput,
    ReaderOutput,
    RunStatus,
    ScriptJson,
    SourceQuote,
    StoryFact,
    StoryBible,
    StoryBibleChapter,
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


class LlmWorkflowError(Exception):
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
        except LlmWorkflowError as exc:
            self.store.fail(run_id, RunStatus.failed_llm, str(exc))
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
        except LlmWorkflowError as exc:
            self.store.fail(run_id, RunStatus.failed_llm, str(exc))
        except Exception as exc:  # pragma: no cover - integration guard
            self.store.fail(run_id, RunStatus.failed_internal, str(exc))

    def _build_plan_graph(self):
        builder = StateGraph(WorkflowState)
        builder.add_node("validate_input", self._validate_input)
        builder.add_node("parse_chapters", self._parse_chapters)
        builder.add_node("read_chapters_individually", self._read_chapters_individually)
        builder.add_node("build_story_bible", self._build_story_bible)
        builder.add_node("plan_adaptation", self._plan_adaptation)

        builder.set_entry_point("validate_input")
        builder.add_edge("validate_input", "parse_chapters")
        builder.add_edge("parse_chapters", "read_chapters_individually")
        builder.add_edge("read_chapters_individually", "build_story_bible")
        builder.add_edge("build_story_bible", "plan_adaptation")
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
            chapter_cards = self.store.read_json(run_id, "chapter_cards.json")
            reader_output = self.store.read_json(run_id, "reader_output.json")
            story_bible = self.store.read_json(run_id, "story_bible.json")
            planner_output = self.store.read_json(run_id, "planner_output.json")
            adaptation_plan = self.store.read_json(run_id, "adaptation_plan.json")
        except Exception as exc:
            raise WorkflowValidationError(
                "Run must complete intake planning before generation."
            ) from exc
        return {
            "run_id": run_id,
            "chapters": chapters,  # type: ignore[typeddict-item]
            "chapter_cards": chapter_cards,  # type: ignore[typeddict-item]
            "reader_output": reader_output,  # type: ignore[typeddict-item]
            "story_bible": story_bible,  # type: ignore[typeddict-item]
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

    def _read_chapters_individually(self, state: WorkflowState) -> WorkflowState:
        self._start_stage(state, "read_chapters_individually")
        chapters = [Chapter.model_validate(item) for item in state["chapters"]]
        if self.llm.mock:
            raw_cards = self._mock_chapter_cards(chapters)
        else:
            raw_cards = [self._remote_chapter_card(chapter) for chapter in chapters]
        chapter_cards = [
            ChapterCard.model_validate(item).model_dump(mode="json") for item in raw_cards
        ]
        reader_output = self._reader_output_from_chapter_cards(chapter_cards)
        self.store.write_json(state["run_id"], "chapter_cards.json", chapter_cards)
        self.store.write_json(state["run_id"], "reader_output.json", reader_output)
        self._finish_stage(
            state,
            "read_chapters_individually",
            f"Created {len(chapter_cards)} chapter cards.",
        )
        return {**state, "chapter_cards": chapter_cards, "reader_output": reader_output}

    def _build_story_bible(self, state: WorkflowState) -> WorkflowState:
        self._start_stage(state, "build_story_bible")
        chapter_cards = [
            ChapterCard.model_validate(item) for item in state["chapter_cards"]
        ]
        if self.llm.mock:
            raw_story_bible = self._mock_story_bible(chapter_cards)
        else:
            raw_story_bible = self._remote_story_bible(state["chapter_cards"])
        story_bible = StoryBible.model_validate(raw_story_bible).model_dump(mode="json")
        self.store.write_json(state["run_id"], "story_bible.json", story_bible)
        self.store.write_text(state["run_id"], "story_bible.md", _story_bible_markdown(story_bible))
        self._finish_stage(
            state,
            "build_story_bible",
            f"Story Bible built from {len(chapter_cards)} chapter cards.",
        )
        return {**state, "story_bible": story_bible}

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
        chapter_cards = [
            ChapterCard.model_validate(item) for item in state["chapter_cards"]
        ]
        story_bible = StoryBible.model_validate(state["story_bible"])
        if self.llm.mock:
            raw_planner_output = self._mock_planner_output(chapter_cards, story_bible)
        else:
            raw_planner_output = self._remote_planner_output(
                state["reader_output"], state["chapter_cards"], state["story_bible"]
            )
        planner_output = PlannerOutput.model_validate(raw_planner_output).model_dump(mode="json")
        adaptation_plan = self._build_adaptation_plan(
            chapters,
            state["reader_output"],
            planner_output,
            story_bible,
            chapter_cards,
        )
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
                state["chapter_cards"],
                state["story_bible"],
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

    def _mock_chapter_cards(self, chapters: list[Chapter]) -> list[dict[str, Any]]:
        cards = []
        for chapter in chapters:
            excerpt = chapter.text[:160]
            key_event = excerpt.rstrip("。！？\n") or chapter.title
            characters = [
                name
                for name in ["林夏", "周砚", "父亲"]
                if name in chapter.text or name in chapter.title
            ] or ["主角"]
            locations = [
                name
                for name in ["城南档案馆", "旧剧院", "城北钟楼", "雨巷"]
                if name in chapter.text
            ] or ["未明确地点"]
            clues = [
                clue
                for clue in ["没有编号的信", "旧剧院", "第三幕台词", "城北钟楼"]
                if clue in chapter.text
            ] or [f"{chapter.title} 的关键线索"]
            card = ChapterCard(
                chapter_id=f"ch_{chapter.index:03d}",
                chapter_index=chapter.index,
                title=chapter.title,
                char_count=chapter.char_count,
                summary=f"{chapter.title} 建立了故事推进所需的线索、人物行动和情绪转折。",
                key_events=[key_event],
                characters=characters,
                locations=locations,
                conflicts=[
                    "主角必须判断线索是否可信，并决定是否继续追查。"
                ],
                emotional_beats=["疑惑", "警觉", "行动"],
                clues=clues,
                adaptation_opportunities=[
                    "把内心判断外化为动作、停顿和对物件的检查。",
                    "保留原章节氛围，同时增加可表演的冲突压力。",
                ],
                source_quotes=[
                    SourceQuote(
                        quote=excerpt,
                        reason="代表本章核心线索或情绪氛围。",
                        confidence="medium",
                    )
                ],
                continuity_notes=[
                    f"本章应在后续改编中保留为第 {chapter.index} 章来源。"
                ],
            )
            cards.append(card.model_dump(mode="json"))
        return cards

    def _reader_output_from_chapter_cards(
        self, chapter_cards: list[dict[str, Any]]
    ) -> dict[str, Any]:
        facts: list[StoryFact] = []
        seen: set[tuple[str, str, int]] = set()
        for payload in chapter_cards:
            card = ChapterCard.model_validate(payload)
            for name in card.characters:
                key = ("character", name, card.chapter_index)
                if key not in seen:
                    facts.append(
                        StoryFact(
                            kind="character",
                            name=name,
                            description=f"{name} appears in {card.title}: {card.summary}",
                            source_chapter=card.chapter_index,
                        )
                    )
                    seen.add(key)
            for name in card.locations:
                key = ("location", name, card.chapter_index)
                if key not in seen:
                    facts.append(
                        StoryFact(
                            kind="location",
                            name=name,
                            description=f"{name} is a location or setting in {card.title}.",
                            source_chapter=card.chapter_index,
                        )
                    )
                    seen.add(key)
            for index, event in enumerate(card.key_events or [card.summary], start=1):
                facts.append(
                    StoryFact(
                        kind="event",
                        name=f"{card.title} 事件 {index}",
                        description=event,
                        source_chapter=card.chapter_index,
                    )
                )
            for clue in card.clues[:3]:
                facts.append(
                    StoryFact(
                        kind="prop",
                        name=clue,
                        description=f"{clue} is tracked as a clue from {card.title}.",
                        source_chapter=card.chapter_index,
                    )
                )
        if not facts:
            facts.append(
                StoryFact(
                    kind="event",
                    name="未命名事件",
                    description="Fallback event created from chapter cards.",
                    source_chapter=1,
                )
            )
        return {"facts": [fact.model_dump(mode="json") for fact in facts]}

    def _mock_story_bible(self, chapter_cards: list[ChapterCard]) -> dict[str, Any]:
        chapter_index = [
            StoryBibleChapter(
                chapter_id=card.chapter_id,
                title=card.title,
                char_count=card.char_count,
                summary=card.summary,
            )
            for card in chapter_cards
        ]
        scope = [card.chapter_index for card in chapter_cards[:3]]
        bible = StoryBible(
            main_plot=(
                "主角沿着章节中的线索逐步逼近真相；改编时应先保留线索链，"
                "再把心理与氛围转换成可见行动。"
            ),
            character_arcs=[
                "林夏：从被动发现线索，到主动追查父亲失踪的真相。",
                "周砚：从守口如瓶的知情者，转为推动主角进入旧剧院秘密的人。",
            ],
            relationship_map=[
                "林夏与父亲：缺席关系通过信件和旧剧本延续。",
                "林夏与周砚：怀疑和试探构成早期戏剧张力。",
            ],
            timeline=[
                f"{card.title}: {card.summary}" for card in chapter_cards[:8]
            ],
            major_clues=[
                clue
                for card in chapter_cards
                for clue in card.clues[:2]
            ][:10],
            adaptation_risks=[
                "长篇小说容易在计划阶段丢失章节覆盖，需要逐章保留理解卡。",
                "心理和氛围描写较多时，剧本必须转换成动作、对白和场景冲突。",
                "不建议一次生成全书剧本，应先生成推荐范围供作者确认。",
            ],
            chapter_index=chapter_index,
            recommended_generation_scope=scope,
        )
        return bible.model_dump(mode="json")

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

    def _mock_planner_output(
        self, chapter_cards: list[ChapterCard], story_bible: StoryBible
    ) -> dict[str, Any]:
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
        scope = set(story_bible.recommended_generation_scope or [1, 2, 3])
        scoped_cards = [
            card for card in chapter_cards if card.chapter_index in scope
        ] or chapter_cards[:3]
        for index, card in enumerate(scoped_cards[:3], start=1):
            source_excerpt = (
                card.source_quotes[0].quote if card.source_quotes else card.summary
            )
            scenes.append(
                {
                    "id": f"sc_{index:03d}",
                    "title": card.title.replace("章", "幕", 1),
                    "source_chapters": [card.chapter_index],
                    "dramatic_purpose": purposes[index - 1],
                    "key_events": card.key_events or [card.summary],
                    "conflict": conflicts[index - 1],
                    "emotional_shift": shifts[index - 1],
                    "source_excerpt": source_excerpt[:220],
                }
            )
        return {"scenes": scenes}

    def _build_adaptation_plan(
        self,
        chapters: list[Chapter],
        reader_output: dict[str, Any],
        planner_output: dict[str, Any],
        story_bible: StoryBible,
        chapter_cards: list[ChapterCard],
    ) -> dict[str, Any]:
        facts = ReaderOutput.model_validate(reader_output).facts
        planner = PlannerOutput.model_validate(planner_output)
        character_notes = [
            f"{fact.name}: {fact.description}"
            for fact in facts
            if fact.kind == "character"
        ][:8]
        plot_threads = [
            *story_bible.timeline[:5],
            *[f"线索：{clue}" for clue in story_bible.major_clues[:5]],
        ][:8]
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
        risks.extend(
            AdaptationRisk(
                severity="warning",
                target="长篇承载",
                message=risk,
                suggestion="先基于章节理解卡确认全书方向，再分章节或分集生成剧本。",
            )
            for risk in story_bible.adaptation_risks[:3]
        )
        scope = story_bible.recommended_generation_scope or [
            chapter.index for chapter in chapters[:3]
        ]
        plan = AdaptationPlan(
            summary=(
                f"{story_bible.main_plot} 建议先生成第 "
                f"{', '.join(str(item) for item in scope)} 章对应的样片段，"
                "让作者确认风格和改编尺度后再继续扩展。"
            ),
            chapter_count=len(chapters),
            recommended_generation_scope=scope,
            rationale=[
                f"系统已生成 {len(chapter_cards)} 张章节理解卡，不切碎章节，保留单章语义连贯。",
                "先用 Story Bible 把主线、人物弧线和线索链合并，再做剧本规划。",
                "默认只生成推荐章节范围，避免长篇一次性生成导致失控或幻觉。",
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
        return self._remote_json(
            "Extract characters, locations, events, and props. Return JSON only matching the provided ReaderOutput schema.",
            {
                "schema": ReaderOutput.model_json_schema(),
                "chapters": [chapter.model_dump() for chapter in chapters],
            },
        )

    def _remote_chapter_card(self, chapter: Chapter) -> dict[str, Any]:
        return self._remote_json(
            (
                "Read one complete novel chapter as the smallest semantic unit. "
                "Return JSON only matching the ChapterCard schema. Preserve chapter meaning; "
                "do not invent facts that are not supported by this chapter."
            ),
            {
                "schema": ChapterCard.model_json_schema(),
                "chapter": chapter.model_dump(mode="json"),
                "chapter_id": f"ch_{chapter.index:03d}",
            },
        )

    def _remote_story_bible(self, chapter_cards: list[dict[str, Any]]) -> dict[str, Any]:
        return self._remote_json(
            (
                "Synthesize a whole-novel Story Bible from chapter cards. "
                "Return JSON only matching the StoryBible schema. Recommend a small generation "
                "scope, usually the first three chapters, instead of generating the whole novel."
            ),
            {
                "schema": StoryBible.model_json_schema(),
                "chapter_cards": chapter_cards,
            },
        )

    def _remote_planner_output(
        self,
        reader_output: dict[str, Any],
        chapter_cards: list[dict[str, Any]],
        story_bible: dict[str, Any],
    ) -> dict[str, Any]:
        return self._remote_json(
            (
                "Create a concise screenplay scene plan for the Story Bible's recommended "
                "generation scope. Return JSON only matching the PlannerOutput schema. "
                "Each scene must reference source chapters and use evidence from chapter cards."
            ),
            {
                "schema": PlannerOutput.model_json_schema(),
                "reader_output": reader_output,
                "chapter_cards": chapter_cards,
                "story_bible": story_bible,
            },
        )

    def _remote_script(
        self,
        reader_output: dict[str, Any],
        planner_output: dict[str, Any],
        chapter_cards: list[dict[str, Any]],
        story_bible: dict[str, Any],
        adaptation_plan: dict[str, Any],
        author_controls: dict[str, Any],
    ) -> dict[str, Any]:
        return self._remote_json(
            (
                "Generate screenplay JSON matching the provided ScriptJson schema. "
                "Use only the planned scenes, chapter cards, Story Bible, and author controls. "
                "Return JSON only."
            ),
            {
                "schema": script_json_schema(),
                "reader_output": reader_output,
                "planner_output": planner_output,
                "chapter_cards": chapter_cards,
                "story_bible": story_bible,
                "adaptation_plan": adaptation_plan,
                "author_controls": author_controls,
            },
        )

    def _remote_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.llm.generate_json(system_prompt, user_payload)
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            if len(message) > 500:
                message = message[:500] + "..."
            raise LlmWorkflowError(message) from exc

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
    story_bible = StoryBible.model_validate(state.get("story_bible") or {})
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
        "## Long Novel Handling",
        "",
        f"- Story Bible main plot: {story_bible.main_plot}",
        f"- Recommended generation scope: `{', '.join(str(item) for item in plan.recommended_generation_scope)}`",
        f"- Chapter cards used: `{len(story_bible.chapter_index)}`",
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
        f"- Recommended generation scope: `{', '.join(str(item) for item in plan.recommended_generation_scope)}`",
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


def _story_bible_markdown(story_bible_payload: dict[str, Any]) -> str:
    story_bible = StoryBible.model_validate(story_bible_payload)
    lines = [
        "# Story Bible",
        "",
        "## Main Plot",
        "",
        story_bible.main_plot,
        "",
        "## Recommended Generation Scope",
        "",
        f"`{', '.join(str(item) for item in story_bible.recommended_generation_scope)}`",
        "",
        "## Character Arcs",
        "",
    ]
    lines.extend(f"- {item}" for item in story_bible.character_arcs)
    lines.extend(["", "## Relationship Map", ""])
    lines.extend(f"- {item}" for item in story_bible.relationship_map)
    lines.extend(["", "## Timeline", ""])
    lines.extend(f"- {item}" for item in story_bible.timeline)
    lines.extend(["", "## Major Clues", ""])
    lines.extend(f"- {item}" for item in story_bible.major_clues)
    lines.extend(["", "## Adaptation Risks", ""])
    lines.extend(f"- {item}" for item in story_bible.adaptation_risks)
    lines.extend(["", "## Chapter Index", ""])
    for chapter in story_bible.chapter_index:
        lines.append(
            f"- `{chapter.chapter_id}` {chapter.title} ({chapter.char_count} chars): {chapter.summary}"
        )
    return "\n".join(lines) + "\n"
