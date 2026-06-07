import re
from typing import Any
from uuid import uuid4
from langgraph.graph import END, StateGraph

from app.core.config import Settings
from app.domain.chapter_parser import ChapterParseError, parse_chapters
from app.domain.schemas import (
    AdaptationPlan,
    AdaptationRisk,
    AuthorControls,
    Chapter,
    ChapterCard,
    ChapterChatMessage,
    ChapterReview,
    ChapterScriptCard,
    ChapterScriptReview,
    PlannerOutput,
    ReaderOutput,
    RunStatus,
    ScriptJson,
    ScriptFeedback,
    SourceQuote,
    StoryFact,
    StoryBible,
    StoryBibleChapter,
    ValidationReport,
    now_iso,
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


_CHINESE_DIGITS = {
    0: "零",
    1: "一",
    2: "二",
    3: "三",
    4: "四",
    5: "五",
    6: "六",
    7: "七",
    8: "八",
    9: "九",
}


def _chapter_number_markers(index: int) -> list[str]:
    numbers = {str(index)}
    if 0 < index < 100:
        if index < 10:
            numbers.add(_CHINESE_DIGITS[index])
        elif index == 10:
            numbers.add("十")
        elif index < 20:
            numbers.add(f"十{_CHINESE_DIGITS[index % 10]}")
        else:
            ten = index // 10
            one = index % 10
            numbers.add(f"{_CHINESE_DIGITS[ten]}十{_CHINESE_DIGITS[one]}" if one else f"{_CHINESE_DIGITS[ten]}十")
    markers: list[str] = []
    for number in numbers:
        markers.extend([f"第{number}章", f"第 {number} 章"])
    return markers


def _compact_text(value: str, limit: int = 240) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


class AdaptationWorkflow:
    def __init__(self, settings: Settings, store: RunStore):
        self.settings = settings
        self.store = store
        self.llm = LlmClient(settings)
        self.intake_graph = self._build_intake_graph()
        self.plan_graph = self._build_plan_graph()
        self.generate_graph = self._build_generate_graph()

    def _assert_run_status(
        self,
        run_id: str,
        expected: tuple[RunStatus, ...],
        message: str,
    ) -> None:
        if self.store.read_manifest(run_id).status not in expected:
            raise WorkflowValidationError(message)

    def intake(self, run_id: str) -> None:
        try:
            input_text = self.store.read_input(run_id)
            self.intake_graph.invoke({"run_id": run_id, "input_text": input_text})
            self.store.set_stage(
                run_id,
                "awaiting_chapter_review",
                "succeeded",
                message="Chapter cards are ready for author review.",
                run_status=RunStatus.awaiting_chapter_review,
            )
        except (ChapterParseError, WorkflowValidationError) as exc:
            self.store.fail(run_id, RunStatus.failed_validation, str(exc))
        except LlmWorkflowError as exc:
            self.store.fail(run_id, RunStatus.failed_llm, str(exc))
        except Exception as exc:  # pragma: no cover - integration guard
            self.store.fail(run_id, RunStatus.failed_internal, str(exc))

    def plan(self, run_id: str) -> None:
        self.build_plan(run_id)

    def build_plan(self, run_id: str, *, require_approved: bool = True) -> None:
        try:
            if require_approved:
                self._assert_run_status(
                    run_id,
                    (RunStatus.awaiting_chapter_review, RunStatus.planning),
                    "Run is not awaiting chapter review.",
                )
            state = self._load_planning_state(run_id, require_approved=require_approved)
            self.plan_graph.invoke(state)
            self.store.planned(run_id)
        except (ChapterParseError, WorkflowValidationError) as exc:
            self.store.fail(run_id, RunStatus.failed_validation, str(exc))
        except LlmWorkflowError as exc:
            self.store.fail(run_id, RunStatus.failed_llm, str(exc))
        except Exception as exc:  # pragma: no cover - integration guard
            self.store.fail(run_id, RunStatus.failed_internal, str(exc))

    def approve_chapter(self, run_id: str, chapter_id: str) -> None:
        self._assert_run_status(
            run_id,
            (RunStatus.awaiting_chapter_review,),
            "Run is not awaiting chapter review.",
        )
        reviews = self._read_reviews(run_id)
        cards = [
            ChapterCard.model_validate(item)
            for item in self.store.read_json(run_id, "chapter_cards.json")
        ]
        if chapter_id not in {card.chapter_id for card in cards}:
            raise WorkflowValidationError("Chapter card is not ready for approval.")
        reviews = [
            review.model_copy(
                update={
                    "status": "approved",
                    "approved_at": now_iso(),
                    "error": None,
                }
            )
            if review.chapter_id == chapter_id
            else review
            for review in reviews
        ]
        self._write_reviews(run_id, reviews)
        self.store.set_status(run_id, RunStatus.awaiting_chapter_review)

    def approve_all_chapters(self, run_id: str) -> None:
        self._assert_run_status(
            run_id,
            (RunStatus.awaiting_chapter_review,),
            "Run is not awaiting chapter review.",
        )
        reviews = self._read_reviews(run_id)
        cards = [
            ChapterCard.model_validate(item)
            for item in self.store.read_json(run_id, "chapter_cards.json")
        ]
        ready_ids = {card.chapter_id for card in cards}
        reviews = [
            review.model_copy(
                update={
                    "status": "approved",
                    "approved_at": review.approved_at or now_iso(),
                    "error": None,
                }
            )
            if review.chapter_id in ready_ids
            else review
            for review in reviews
        ]
        self._write_reviews(run_id, reviews)
        self.store.set_status(run_id, RunStatus.awaiting_chapter_review)

    def regenerate_chapter(
        self,
        run_id: str,
        chapter_id: str,
        feedback_notes: str | None = None,
    ) -> None:
        try:
            self._assert_run_status(
                run_id,
                (RunStatus.awaiting_chapter_review, RunStatus.regenerating_chapter),
                "Run is not awaiting chapter review.",
            )
            chapters = [
                Chapter.model_validate(item)
                for item in self.store.read_json(run_id, "chapters.json")
            ]
            chapter = next(
                (item for item in chapters if f"ch_{item.index:03d}" == chapter_id),
                None,
            )
            if chapter is None:
                raise WorkflowValidationError("Chapter not found.")
            reviews = self._read_reviews(run_id)
            reviews = [
                review.model_copy(
                    update={"status": "regenerating", "approved_at": None, "error": None}
                )
                if review.chapter_id == chapter_id
                else review
                for review in reviews
            ]
            self._write_reviews(run_id, reviews)
            self.store.set_stage(
                run_id,
                "regenerate_chapter",
                "running",
                message=f"Regenerating {chapter_id}.",
                run_status=RunStatus.regenerating_chapter,
            )
            raw_card = (
                self._mock_chapter_cards([chapter], feedback_notes=feedback_notes)[0]
                if self.llm.mock
                else self._remote_chapter_card(chapter, feedback_notes=feedback_notes)
            )
            new_card = ChapterCard.model_validate(raw_card, extra="ignore").model_dump(mode="json")
            current_cards = [
                ChapterCard.model_validate(item).model_dump(mode="json")
                for item in self.store.read_json(run_id, "chapter_cards.json")
            ]
            replaced = False
            next_cards = []
            for card in current_cards:
                if card["chapter_id"] == chapter_id:
                    next_cards.append(new_card)
                    replaced = True
                else:
                    next_cards.append(card)
            if not replaced:
                next_cards.append(new_card)
            next_cards.sort(key=lambda item: item["chapter_index"])
            self.store.write_json(run_id, "chapter_cards.json", next_cards)
            reviews = [
                review.model_copy(
                    update={
                        "status": "ready",
                        "approved_at": None,
                        "error": None,
                        "revision_count": review.revision_count + 1,
                    }
                )
                if review.chapter_id == chapter_id
                else review
                for review in reviews
            ]
            self._write_reviews(run_id, reviews)
            self.store.remove_artifacts(
                run_id,
                [
                    "reader_output.json",
                    "story_bible.json",
                    "story_bible.md",
                    "planner_output.json",
                    "adaptation_plan.json",
                    "adaptation_plan.md",
                    "author_controls.json",
                    "chapter_script_cards.json",
                    "chapter_script_reviews.json",
                    "chapter_script_feedback.json",
                    "chapter_script_chat_messages.json",
                    "continuity_report.md",
                    "script.json",
                    "script.yaml",
                    "schema.json",
                    "schema.md",
                    "adaptation_report.md",
                    "report.json",
                ],
            )
            self.store.set_stage(
                run_id,
                "regenerate_chapter",
                "succeeded",
                message=f"{chapter_id} regenerated.",
                run_status=RunStatus.awaiting_chapter_review,
            )
        except (WorkflowValidationError, LlmWorkflowError) as exc:
            self._fail_chapter_review(run_id, chapter_id, str(exc))
        except Exception as exc:
            self._fail_chapter_review(run_id, chapter_id, str(exc))

    def generate(self, run_id: str, controls: AuthorControls | dict[str, Any] | None = None) -> None:
        try:
            self._assert_run_status(
                run_id,
                (RunStatus.planned, RunStatus.generating_chapter_scripts),
                "Run is not ready for chapter script generation.",
            )
            author_controls = AuthorControls.model_validate(controls or {})
            self.store.write_json(run_id, "author_controls.json", author_controls.model_dump(mode="json"))
            self.store.set_stage(
                run_id,
                "await_author_controls",
                "succeeded",
                message="Author controls accepted.",
                run_status=RunStatus.generating_chapter_scripts,
            )
            self._generate_chapter_script_cards_for_review(run_id, author_controls)
        except (ChapterParseError, WorkflowValidationError) as exc:
            self.store.fail(run_id, RunStatus.failed_validation, str(exc))
        except LlmWorkflowError as exc:
            self.store.fail(run_id, RunStatus.failed_llm, str(exc))
        except Exception as exc:  # pragma: no cover - integration guard
            self.store.fail(run_id, RunStatus.failed_internal, str(exc))

    def approve_chapter_script(self, run_id: str, chapter_id: str) -> None:
        self._assert_run_status(
            run_id,
            (RunStatus.awaiting_script_review,),
            "Run is not awaiting chapter script review.",
        )
        reviews = self._read_script_reviews(run_id)
        cards = self._read_chapter_script_cards(run_id)
        if chapter_id not in {card.chapter_id for card in cards}:
            raise WorkflowValidationError("Chapter script card is not ready for approval.")
        reviews = [
            review.model_copy(
                update={
                    "status": "approved",
                    "approved_at": now_iso(),
                    "error": None,
                }
            )
            if review.chapter_id == chapter_id
            else review
            for review in reviews
        ]
        self._write_script_reviews(run_id, reviews)
        self.store.set_status(run_id, RunStatus.awaiting_script_review)

    def approve_all_chapter_scripts(self, run_id: str) -> None:
        self._assert_run_status(
            run_id,
            (RunStatus.awaiting_script_review,),
            "Run is not awaiting chapter script review.",
        )
        reviews = self._read_script_reviews(run_id)
        cards = self._read_chapter_script_cards(run_id)
        ready_ids = {card.chapter_id for card in cards}
        reviews = [
            review.model_copy(
                update={
                    "status": "approved",
                    "approved_at": review.approved_at or now_iso(),
                    "error": None,
                }
            )
            if review.chapter_id in ready_ids
            else review
            for review in reviews
        ]
        self._write_script_reviews(run_id, reviews)
        self.store.set_status(run_id, RunStatus.awaiting_script_review)

    def regenerate_chapter_script(
        self,
        run_id: str,
        chapter_id: str,
        feedback: ScriptFeedback | dict[str, Any] | None = None,
    ) -> None:
        try:
            self._assert_run_status(
                run_id,
                (
                    RunStatus.awaiting_script_review,
                    RunStatus.regenerating_chapter_script,
                    RunStatus.awaiting_final_review,
                ),
                "Run is not ready for chapter script regeneration.",
            )
            feedback_model = (
                ScriptFeedback.model_validate(feedback)
                if feedback is not None
                else None
            )
            chapters = [
                Chapter.model_validate(item)
                for item in self.store.read_json(run_id, "chapters.json")
            ]
            chapter_cards = [
                ChapterCard.model_validate(item)
                for item in self.store.read_json(run_id, "chapter_cards.json")
            ]
            author_controls = AuthorControls.model_validate(
                self.store.read_json(run_id, "author_controls.json")
            )
            adaptation_plan = AdaptationPlan.model_validate(
                self.store.read_json(run_id, "adaptation_plan.json")
            )
            chapter = next(
                (item for item in chapters if f"ch_{item.index:03d}" == chapter_id),
                None,
            )
            source_card = next(
                (item for item in chapter_cards if item.chapter_id == chapter_id),
                None,
            )
            if chapter is None or source_card is None:
                raise WorkflowValidationError("Chapter source is not ready for script regeneration.")
            reviews = self._read_script_reviews(run_id)
            reviews = [
                review.model_copy(
                    update={"status": "regenerating", "approved_at": None, "error": None}
                )
                if review.chapter_id == chapter_id
                else review
                for review in reviews
            ]
            self._write_script_reviews(run_id, reviews)
            self.store.set_stage(
                run_id,
                "regenerate_chapter_script",
                "running",
                message=f"Regenerating script card {chapter_id}.",
                run_status=RunStatus.regenerating_chapter_script,
            )
            raw_card = (
                self._mock_chapter_script_card(
                    chapter,
                    source_card,
                    adaptation_plan,
                    author_controls,
                    [feedback_model] if feedback_model else [],
                )
                if self.llm.mock
                else self._remote_chapter_script_card(
                    chapter,
                    source_card,
                    adaptation_plan,
                    author_controls,
                    [feedback_model] if feedback_model else [],
                )
            )
            new_card = ChapterScriptCard.model_validate(
                self._normalize_chapter_script_card_payload(raw_card),
                extra="ignore",
            ).model_dump(mode="json")
            current_cards = [
                card.model_dump(mode="json") for card in self._read_chapter_script_cards(run_id)
            ]
            replaced = False
            next_cards = []
            for card in current_cards:
                if card["chapter_id"] == chapter_id:
                    next_cards.append(new_card)
                    replaced = True
                else:
                    next_cards.append(card)
            if not replaced:
                next_cards.append(new_card)
            next_cards.sort(key=lambda item: item["chapter_index"])
            self.store.write_json(run_id, "chapter_script_cards.json", next_cards)
            reviews = [
                review.model_copy(
                    update={
                        "status": "ready",
                        "approved_at": None,
                        "error": None,
                        "revision_count": review.revision_count + 1,
                    }
                )
                if review.chapter_id == chapter_id
                else review
                for review in reviews
            ]
            self._write_script_reviews(run_id, reviews)
            self.store.remove_artifacts(
                run_id,
                [
                    "script.json",
                    "script.yaml",
                    "schema.json",
                    "schema.md",
                    "adaptation_report.md",
                    "report.json",
                    "continuity_report.md",
                ],
            )
            self.store.set_stage(
                run_id,
                "regenerate_chapter_script",
                "succeeded",
                message=f"{chapter_id} script card regenerated.",
                run_status=RunStatus.awaiting_script_review,
            )
        except (WorkflowValidationError, LlmWorkflowError) as exc:
            self._fail_chapter_script_review(run_id, chapter_id, str(exc))
        except Exception as exc:
            self._fail_chapter_script_review(run_id, chapter_id, str(exc))

    def continuity_merge(self, run_id: str, feedback: ScriptFeedback | dict[str, Any] | None = None) -> None:
        try:
            feedback_model = (
                ScriptFeedback.model_validate(feedback)
                if feedback is not None
                else None
            )
            self._assert_run_status(
                run_id,
                (RunStatus.awaiting_final_review, RunStatus.awaiting_script_review)
                if feedback_model
                else (RunStatus.awaiting_script_review, RunStatus.merging_continuity),
                "Run is not ready for continuity merge.",
            )
            self._assert_script_reviews_approved(run_id)
            author_controls = AuthorControls.model_validate(
                self.store.read_json(run_id, "author_controls.json")
            )
            state = self._load_generation_state(run_id, author_controls)
            state["chapter_script_cards"] = [
                card.model_dump(mode="json") for card in self._read_chapter_script_cards(run_id)
            ]  # type: ignore[typeddict-item]
            if feedback_model:
                state["final_feedback"] = feedback_model.model_dump(mode="json")  # type: ignore[typeddict-item]
            self.store.set_stage(
                run_id,
                "continuity_merge",
                "running",
                message="Merging approved chapter script cards into one coherent script.",
                run_status=RunStatus.merging_continuity,
            )
            self.store.write_text(
                run_id,
                "continuity_report.md",
                _continuity_report_markdown(
                    self._read_chapter_script_cards(run_id),
                    feedback_model,
                ),
            )
            self.generate_graph.invoke(state)
            self.store.set_stage(
                run_id,
                "continuity_merge",
                "succeeded",
                message="Continuity merge completed. Final script awaits author review.",
                run_status=RunStatus.awaiting_final_review,
            )
        except (ChapterParseError, WorkflowValidationError) as exc:
            self.store.fail(run_id, RunStatus.failed_validation, str(exc))
        except LlmWorkflowError as exc:
            self.store.fail(run_id, RunStatus.failed_llm, str(exc))
        except Exception as exc:  # pragma: no cover - integration guard
            self.store.fail(run_id, RunStatus.failed_internal, str(exc))

    def create_final_feedback(
        self,
        run_id: str,
        category: str,
        complaint: str,
        desired_change: str = "",
    ) -> ScriptFeedback:
        self._assert_final_review_ready(run_id)
        cards = self._read_chapter_script_cards(run_id)
        target_chapter_id: str | None = None
        target_scene_id: str | None = None
        target_type = (
            "continuity"
            if category == "continuity"
            else "chapter_and_continuity"
            if category == "chapter_and_continuity"
            else "chapter_script"
        )
        if category != "continuity":
            target_chapter_id, target_scene_id = self._infer_feedback_target(complaint, cards)
        feedback = ScriptFeedback(
            id=str(uuid4()),
            source="final_review",
            target_type=target_type,  # type: ignore[arg-type]
            target_chapter_id=target_chapter_id,
            target_scene_id=target_scene_id,
            complaint=complaint,
            desired_change=desired_change,
            ai_assessment=(
                "这是连贯性问题，建议保留已通过章节剧本卡，只重新做跨章衔接合成。"
                if category == "continuity"
                else (
                    f"我判断这个问题最可能落在 {target_chapter_id or '待确认章节'}。"
                    "系统会先重写该章剧本卡，再带着反馈自动重新做连贯性合成。"
                )
                if category == "chapter_and_continuity"
                else (
                    f"我判断这个问题最可能落在 {target_chapter_id or '待确认章节'}。"
                    "系统会先重写该章剧本卡，再自动重新做连贯性合成。"
                )
            ),
            created_at=now_iso(),
        )
        feedbacks = self._read_feedback(run_id)
        feedbacks.append(feedback)
        self._write_feedback(run_id, feedbacks)
        return feedback

    def apply_final_feedback(
        self,
        run_id: str,
        feedback_id: str,
        confirmed_chapter_id: str | None = None,
    ) -> ScriptFeedback:
        self._assert_final_review_ready(run_id)
        feedbacks = self._read_feedback(run_id)
        feedback = next((item for item in feedbacks if item.id == feedback_id), None)
        if feedback is None:
            raise WorkflowValidationError("Feedback not found.")
        if feedback.target_type == "continuity":
            applied = feedback.model_copy(update={"status": "applied", "applied_at": now_iso()})
            feedbacks = [applied if item.id == feedback_id else item for item in feedbacks]
            self._write_feedback(run_id, feedbacks)
            self.continuity_merge(run_id, applied)
            return applied
        chapter_id = confirmed_chapter_id
        if not chapter_id:
            raise WorkflowValidationError("A chapter confirmation is required before applying this feedback.")
        if chapter_id not in {card.chapter_id for card in self._read_chapter_script_cards(run_id)}:
            raise WorkflowValidationError("Confirmed chapter script card does not exist.")
        applied = feedback.model_copy(
            update={
                "status": "applied",
                "target_chapter_id": chapter_id,
                "applied_at": now_iso(),
            }
        )
        feedbacks = [applied if item.id == feedback_id else item for item in feedbacks]
        self._write_feedback(run_id, feedbacks)
        self.regenerate_chapter_script(run_id, chapter_id, applied)
        target_review = next(
            (review for review in self._read_script_reviews(run_id) if review.chapter_id == chapter_id),
            None,
        )
        if target_review and target_review.status == "ready":
            self.approve_chapter_script(run_id, chapter_id)
            self.continuity_merge(run_id, applied)
        return applied

    def _assert_final_review_ready(self, run_id: str) -> None:
        manifest = self.store.read_manifest(run_id)
        if manifest.status != RunStatus.awaiting_final_review or "script.yaml" not in manifest.artifacts:
            raise WorkflowValidationError("Final feedback is only available while the run is awaiting final review.")

    def _build_intake_graph(self):
        builder = StateGraph(WorkflowState)
        builder.add_node("validate_input", self._validate_input)
        builder.add_node("parse_chapters", self._parse_chapters)
        builder.add_node("read_chapters_individually", self._read_chapters_individually)

        builder.set_entry_point("validate_input")
        builder.add_edge("validate_input", "parse_chapters")
        builder.add_edge("parse_chapters", "read_chapters_individually")
        builder.add_edge("read_chapters_individually", END)
        return builder.compile()

    def _build_plan_graph(self):
        builder = StateGraph(WorkflowState)
        builder.add_node("build_story_bible", self._build_story_bible)
        builder.add_node("plan_adaptation", self._plan_adaptation)

        builder.set_entry_point("build_story_bible")
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

    def _load_planning_state(
        self, run_id: str, *, require_approved: bool
    ) -> WorkflowState:
        chapters_payload = self.store.read_json(run_id, "chapters.json")
        chapter_cards_payload = self.store.read_json(run_id, "chapter_cards.json")
        reviews = [
            ChapterReview.model_validate(item)
            for item in self.store.read_json(run_id, "chapter_reviews.json")
        ]
        cards_by_id = {
            ChapterCard.model_validate(item).chapter_id: item
            for item in chapter_cards_payload
        }
        if require_approved:
            not_ready = [
                review.chapter_id
                for review in reviews
                if review.status != "approved" or review.chapter_id not in cards_by_id
            ]
            if not_ready:
                raise WorkflowValidationError(
                    "All chapter cards must be approved before building the adaptation plan."
                )
        approved_ids = {
            review.chapter_id
            for review in reviews
            if review.status == "approved" and review.chapter_id in cards_by_id
        }
        if not approved_ids:
            approved_ids = set(cards_by_id)
        approved_cards = [
            card
            for card in chapter_cards_payload
            if ChapterCard.model_validate(card).chapter_id in approved_ids
        ]
        if len(approved_cards) < 3:
            raise WorkflowValidationError(
                "At least 3 approved chapter cards are required to build the adaptation plan."
            )
        reader_output = self._reader_output_from_chapter_cards(approved_cards)
        self.store.write_json(run_id, "reader_output.json", reader_output)
        return {
            "run_id": run_id,
            "chapters": chapters_payload,  # type: ignore[typeddict-item]
            "chapter_cards": approved_cards,  # type: ignore[typeddict-item]
            "reader_output": reader_output,  # type: ignore[typeddict-item]
        }

    def _read_reviews(self, run_id: str) -> list[ChapterReview]:
        return [
            ChapterReview.model_validate(item)
            for item in self.store.read_json(run_id, "chapter_reviews.json")
        ]

    def _write_reviews(self, run_id: str, reviews: list[ChapterReview]) -> None:
        self.store.write_json(
            run_id,
            "chapter_reviews.json",
            [review.model_dump(mode="json") for review in reviews],
        )

    def _fail_chapter_review(self, run_id: str, chapter_id: str, error: str) -> None:
        try:
            reviews = self._read_reviews(run_id)
            reviews = [
                review.model_copy(
                    update={"status": "failed", "approved_at": None, "error": error}
                )
                if review.chapter_id == chapter_id
                else review
                for review in reviews
            ]
            self._write_reviews(run_id, reviews)
            self.store.set_stage(
                run_id,
                "regenerate_chapter",
                "failed",
                message=error,
                run_status=RunStatus.awaiting_chapter_review,
            )
        except Exception:
            self.store.fail(run_id, RunStatus.failed_internal, error)

    def _read_script_reviews(self, run_id: str) -> list[ChapterScriptReview]:
        return [
            ChapterScriptReview.model_validate(item)
            for item in self.store.read_json(run_id, "chapter_script_reviews.json")
        ]

    def _write_script_reviews(
        self, run_id: str, reviews: list[ChapterScriptReview]
    ) -> None:
        self.store.write_json(
            run_id,
            "chapter_script_reviews.json",
            [review.model_dump(mode="json") for review in reviews],
        )

    def _fail_chapter_script_review(self, run_id: str, chapter_id: str, error: str) -> None:
        try:
            reviews = self._read_script_reviews(run_id)
            reviews = [
                review.model_copy(
                    update={"status": "failed", "approved_at": None, "error": error}
                )
                if review.chapter_id == chapter_id
                else review
                for review in reviews
            ]
            self._write_script_reviews(run_id, reviews)
            self.store.set_stage(
                run_id,
                "regenerate_chapter_script",
                "failed",
                message=error,
                run_status=RunStatus.awaiting_script_review,
            )
        except Exception:
            self.store.fail(run_id, RunStatus.failed_internal, error)

    def _read_chapter_script_cards(self, run_id: str) -> list[ChapterScriptCard]:
        return [
            ChapterScriptCard.model_validate(item)
            for item in self.store.read_json(run_id, "chapter_script_cards.json")
        ]

    def _read_feedback(self, run_id: str) -> list[ScriptFeedback]:
        try:
            payload = self.store.read_json(run_id, "chapter_script_feedback.json")
        except Exception:
            payload = []
        return [ScriptFeedback.model_validate(item) for item in payload]

    def _write_feedback(self, run_id: str, feedbacks: list[ScriptFeedback]) -> None:
        self.store.write_json(
            run_id,
            "chapter_script_feedback.json",
            [feedback.model_dump(mode="json") for feedback in feedbacks],
        )

    def _assert_script_reviews_approved(self, run_id: str) -> None:
        reviews = self._read_script_reviews(run_id)
        cards = self._read_chapter_script_cards(run_id)
        cards_by_id = {card.chapter_id for card in cards}
        blocked = [
            review.chapter_id
            for review in reviews
            if review.status != "approved" or review.chapter_id not in cards_by_id
        ]
        if not reviews or not cards:
            raise WorkflowValidationError(
                "Chapter script cards must be generated before continuity merge."
            )
        if blocked:
            raise WorkflowValidationError(
                "All chapter script cards must be approved before continuity merge."
            )

    def _generate_chapter_script_cards_for_review(
        self,
        run_id: str,
        author_controls: AuthorControls,
    ) -> None:
        state = self._load_generation_state(run_id, author_controls)
        chapters = [Chapter.model_validate(item) for item in state["chapters"]]
        chapter_cards = [
            ChapterCard.model_validate(item) for item in state["chapter_cards"]
        ]
        reviews = [
            ChapterReview.model_validate(item)
            for item in self.store.read_json(run_id, "chapter_reviews.json")
        ]
        approved_ids = {
            review.chapter_id
            for review in reviews
            if review.status == "approved"
        }
        if len(approved_ids) < 3:
            raise WorkflowValidationError(
                "Chapter summary cards must be approved before script cards can be generated."
            )
        story_bible = StoryBible.model_validate(state["story_bible"])
        adaptation_plan = AdaptationPlan.model_validate(state["adaptation_plan"])
        approved_cards = sorted(
            [card for card in chapter_cards if card.chapter_id in approved_ids],
            key=lambda item: item.chapter_index,
        )
        approved_indexes = {card.chapter_index for card in approved_cards}
        requested_scope = author_controls.generation_scope
        unknown_scope = [
            index for index in requested_scope if index not in approved_indexes
        ]
        if unknown_scope:
            raise WorkflowValidationError(
                f"Selected generation chapters are not approved or do not exist: {unknown_scope}."
            )
        scope = set(
            requested_scope
            or story_bible.recommended_generation_scope
            or adaptation_plan.recommended_generation_scope
            or [1, 2, 3]
        )
        source_cards = [
            card
            for card in approved_cards
            if card.chapter_index in scope
        ]
        if not source_cards:
            raise WorkflowValidationError(
                "Select at least one approved chapter before generating script cards."
            )
        min_card_count = min(3, len(approved_cards))
        if not requested_scope and len(source_cards) < min_card_count:
            selected_ids = {card.chapter_id for card in source_cards}
            for card in approved_cards:
                if card.chapter_id in selected_ids:
                    continue
                source_cards.append(card)
                selected_ids.add(card.chapter_id)
                if len(source_cards) >= min_card_count:
                    break
        source_cards.sort(key=lambda item: item.chapter_index)
        chapters_by_id = {f"ch_{chapter.index:03d}": chapter for chapter in chapters}
        script_reviews = [
            ChapterScriptReview(chapter_id=card.chapter_id, status="pending")
            for card in source_cards
        ]
        self._write_script_reviews(run_id, script_reviews)
        self.store.set_stage(
            run_id,
            "generate_chapter_script_cards",
            "running",
            message=f"Generating {len(source_cards)} chapter script cards.",
            run_status=RunStatus.generating_chapter_scripts,
        )
        script_cards: list[dict[str, Any]] = []
        for card in source_cards:
            chapter = chapters_by_id.get(card.chapter_id)
            if chapter is None:
                continue
            script_reviews = [
                review.model_copy(update={"status": "generating", "error": None})
                if review.chapter_id == card.chapter_id
                else review
                for review in script_reviews
            ]
            self._write_script_reviews(run_id, script_reviews)
            raw_script_card = (
                self._mock_chapter_script_card(
                    chapter,
                    card,
                    adaptation_plan,
                    author_controls,
                    [],
                )
                if self.llm.mock
                else self._remote_chapter_script_card(
                    chapter,
                    card,
                    adaptation_plan,
                    author_controls,
                    [],
                )
            )
            script_card = ChapterScriptCard.model_validate(
                self._normalize_chapter_script_card_payload(raw_script_card),
                extra="ignore",
            ).model_dump(mode="json")
            script_cards.append(script_card)
            self.store.write_json(run_id, "chapter_script_cards.json", script_cards)
            script_reviews = [
                review.model_copy(update={"status": "ready", "error": None})
                if review.chapter_id == card.chapter_id
                else review
                for review in script_reviews
            ]
            self._write_script_reviews(run_id, script_reviews)
            self._append_workflow_event(
                run_id,
                "chapter_script_card_ready",
                {"chapter_id": card.chapter_id},
            )
        self.store.remove_artifacts(
            run_id,
            [
                "script.json",
                "script.yaml",
                "schema.json",
                "schema.md",
                "adaptation_report.md",
                "report.json",
                "continuity_report.md",
            ],
        )
        self.store.set_stage(
            run_id,
            "generate_chapter_script_cards",
            "succeeded",
            message=f"Created {len(script_cards)} chapter script cards.",
        )
        self.store.set_stage(
            run_id,
            "awaiting_script_review",
            "succeeded",
            message="Chapter script cards are ready for author review.",
            run_status=RunStatus.awaiting_script_review,
        )

    @staticmethod
    def _infer_feedback_target(
        complaint: str,
        cards: list[ChapterScriptCard],
    ) -> tuple[str | None, str | None]:
        for card in cards:
            markers = [
                *_chapter_number_markers(card.chapter_index),
                card.chapter_id,
                card.title,
            ]
            if any(marker and marker in complaint for marker in markers):
                scene_id = card.scenes[0].id if card.scenes else None
                return card.chapter_id, scene_id
        for card in cards:
            for scene in card.scenes:
                if scene.title and scene.title in complaint:
                    return card.chapter_id, scene.id
        if cards:
            first = cards[0]
            return first.chapter_id, first.scenes[0].id if first.scenes else None
        return None, None

    def _append_workflow_event(
        self, run_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        try:
            events = list(self.store.read_json(run_id, "workflow_events.json"))
        except Exception:
            events = []
        events.append(
            {
                "type": event_type,
                "payload": payload,
                "created_at": now_iso(),
            }
        )
        self.store.write_json(run_id, "workflow_events.json", events)

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
        reviews = [
            ChapterReview(chapter_id=f"ch_{chapter.index:03d}")
            for chapter in chapters
        ]
        self._write_reviews(state["run_id"], reviews)
        self.store.write_json(state["run_id"], "workflow_events.json", [])
        self._finish_stage(state, "parse_chapters", f"Detected {len(chapters)} chapters.")
        return {**state, "chapters": chapter_payloads}

    def _read_chapters_individually(self, state: WorkflowState) -> WorkflowState:
        self._start_stage(
            state,
            "read_chapters_individually",
            RunStatus.reading_chapters,
        )
        chapters = [Chapter.model_validate(item) for item in state["chapters"]]
        reviews = self._read_reviews(state["run_id"])
        cards_by_id: dict[str, dict[str, Any]] = {}
        for chapter in chapters:
            chapter_id = f"ch_{chapter.index:03d}"
            reviews = [
                review.model_copy(update={"status": "reading", "error": None})
                if review.chapter_id == chapter_id
                else review
                for review in reviews
            ]
            self._write_reviews(state["run_id"], reviews)
            try:
                raw_card = (
                    self._mock_chapter_cards([chapter])[0]
                    if self.llm.mock
                    else self._remote_chapter_card(chapter)
                )
                card = ChapterCard.model_validate(raw_card, extra="ignore").model_dump(mode="json")
                cards_by_id[chapter_id] = card
                reviews = [
                    review.model_copy(update={"status": "ready", "error": None})
                    if review.chapter_id == chapter_id
                    else review
                    for review in reviews
                ]
                self.store.write_json(
                    state["run_id"],
                    "chapter_cards.json",
                    list(cards_by_id.values()),
                )
                self._append_workflow_event(
                    state["run_id"],
                    "chapter_card_ready",
                    {"chapter_id": chapter_id},
                )
            except Exception as exc:
                reviews = [
                    review.model_copy(update={"status": "failed", "error": str(exc)})
                    if review.chapter_id == chapter_id
                    else review
                    for review in reviews
                ]
                self._write_reviews(state["run_id"], reviews)
                raise
            self._write_reviews(state["run_id"], reviews)
        chapter_cards = list(cards_by_id.values())
        reader_output = self._reader_output_from_chapter_cards(chapter_cards)
        self.store.write_json(state["run_id"], "chapter_cards.json", chapter_cards)
        self._finish_stage(
            state,
            "read_chapters_individually",
            f"Created {len(chapter_cards)} chapter cards.",
        )
        return {**state, "chapter_cards": chapter_cards, "reader_output": reader_output}

    def _build_story_bible(self, state: WorkflowState) -> WorkflowState:
        self._start_stage(state, "build_story_bible", RunStatus.planning)
        chapter_cards = [
            ChapterCard.model_validate(item) for item in state["chapter_cards"]
        ]
        if self.llm.mock:
            raw_story_bible = self._mock_story_bible(chapter_cards)
        else:
            raw_story_bible = self._remote_story_bible(state["chapter_cards"])
        story_bible = StoryBible.model_validate(raw_story_bible, extra="ignore").model_dump(mode="json")
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
        reader_output = ReaderOutput.model_validate(raw_reader_output, extra="ignore").model_dump(mode="json")
        self.store.write_json(state["run_id"], "reader_output.json", reader_output)
        self._finish_stage(state, "extract_story_facts", "Story facts extracted.")
        return {**state, "reader_output": reader_output}

    def _plan_adaptation(self, state: WorkflowState) -> WorkflowState:
        self._start_stage(state, "plan_adaptation", RunStatus.planning)
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
        planner_output = PlannerOutput.model_validate(
            self._normalize_planner_output_payload(raw_planner_output),
            extra="ignore",
        ).model_dump(mode="json")
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
        if state.get("chapter_script_cards"):
            payload = self._script_from_chapter_script_cards(
                chapters,
                [
                    ChapterScriptCard.model_validate(item)
                    for item in state["chapter_script_cards"]
                ],
                adaptation_plan,
                author_controls,
                (
                    ScriptFeedback.model_validate(state["final_feedback"])
                    if state.get("final_feedback")
                    else None
                ),
            )
        elif self.llm.mock:
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

    def _mock_chapter_cards(
        self,
        chapters: list[Chapter],
        feedback_notes: str | None = None,
    ) -> list[dict[str, Any]]:
        cards = []
        feedback_summary = _compact_text(feedback_notes or "", 180)
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
            adaptation_opportunities = [
                "把内心判断外化为动作、停顿和对物件的检查。",
                "保留原章节氛围，同时增加可表演的冲突压力。",
            ]
            continuity_notes = [
                f"本章应在后续改编中保留为第 {chapter.index} 章来源。"
            ]
            if feedback_summary:
                adaptation_opportunities.insert(
                    0,
                    f"重读时优先校正作者指出的问题：{feedback_summary}",
                )
                continuity_notes.append(f"作者讨论反馈：{feedback_summary}")
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
                adaptation_opportunities=adaptation_opportunities,
                source_quotes=[
                    SourceQuote(
                        quote=excerpt,
                        reason="代表本章核心线索或情绪氛围。",
                        confidence="medium",
                    )
                ],
                continuity_notes=continuity_notes,
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
        titles = [
            "雨巷里的信",
            "旧剧院的灯",
            "第三幕台词",
            "线索排成时间线",
            "钟楼前的决定",
        ]
        purposes = [
            "用一封没有编号的信引出父亲失踪线索，让观众在第一场就看到林夏被迫行动。",
            "让周砚作为知情者登场，把旧剧院从背景变成林夏必须面对的阻力。",
            "把旧剧本里的文字谜题转成可见的解谜动作，并把目标推进到城北钟楼。",
            "把本章压缩成一个高压转折点，让线索从被动出现变成主角主动重排。",
            "解决眼前疑问，同时留出下一集或下一场的行动钩子。",
        ]
        source_functions = [
            "本章负责交代主角处境、父亲失踪线索和第一个悬疑钩子。",
            "本章负责扩展人物关系，让父亲过去的知情者与主角正面相遇。",
            "本章负责揭示线索规则，把谜题升级为明确的行动路线。",
            "本章负责把零散线索合并成阶段性判断，推动主角从追随线索变成制定计划。",
            "本章负责给当前小段落收束，同时打开更大的危险。",
        ]
        treatments = [
            "保留信件、雨夜和档案馆氛围，把林夏的疑惑改成翻档案、核对编号、停顿收信等动作。",
            "保留旧剧院和舞台灯，把周砚的隐瞒设计成阻拦、沉默和试探，不让对白一次性解释完。",
            "保留第三幕台词线索，把阅读文字改成圈字、连线、发现地址的连续动作。",
            "保留本章核心线索，把叙述段落压成一场限时整理和被打断的场面。",
            "保留结论，但把结论放在一个新的行动决定里，避免只是讲清楚发生了什么。",
        ]
        reasons = [
            "原文的心理判断不能直接表演，所以把“她意识到异常”改成观众能看见的调查动作。",
            "知情者如果只解释背景会变成说明书，因此要用阻拦和回避制造冲突。",
            "文字谜题适合被外化成道具动作，这样观众能跟着主角一起发现答案。",
            "长篇中间章节容易散，先找出转折功能，再决定是否合并或压缩。",
            "短剧需要每场结尾有推进或反问，所以收束信息时也要保留下一步行动压力。",
        ]
        performance_notes = [
            "重点放在手部翻找、灯光停顿和信封细节，让悬疑从物件里长出来。",
            "让周砚站在门或灯之间，用走位表达“他知道但不愿说”。",
            "用铅笔圈字、纸页翻动和地址成形的过程替代内心独白。",
            "加入倒计时、门外声音或电话打断，让整理线索不变成静态讲解。",
            "让角色带着未说完的话离开，保留观众继续追的欲望。",
        ]
        risk_notes = [
            "不要用旁白一次性解释父亲往事，第一场只给钩子。",
            "周砚不能太快交代真相，否则旧剧院的悬念会塌掉。",
            "解谜过程要让观众看懂，但不要让台词重复解释每一步。",
            "如果线索太多，优先保留推动行动的那一条。",
            "不要把结尾写成总结陈词，要留下新的选择。",
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
                    "title": titles[index - 1] if index <= len(titles) else card.title,
                    "source_chapters": [card.chapter_index],
                    "dramatic_purpose": purposes[index - 1],
                    "key_events": card.key_events or [card.summary],
                    "conflict": conflicts[index - 1],
                    "emotional_shift": shifts[index - 1],
                    "source_excerpt": source_excerpt[:220],
                    "source_function": source_functions[index - 1],
                    "adaptation_treatment": treatments[index - 1],
                    "adaptation_reason": reasons[index - 1],
                    "performance_notes": performance_notes[index - 1],
                    "risk_note": risk_notes[index - 1],
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
        creative_rationale = [
            (
                "前三章已经形成“发现线索 -> 进入旧剧院 -> 读出台词地址”的连续钩子，"
                "适合短剧按章节落成三场戏，每场结尾都能推动下一步。"
            ),
            (
                "主角的疑惑、警觉和决心主要藏在心理描写里，选择心理外化可以把这些内容改成"
                "翻找、停顿、试探和克制对白。"
            ),
            (
                "父亲失踪和线索链是原著味道的核心，平衡改编比大胆改编更稳：保留动机和线索，"
                "只增强冲突、节奏和可表演动作。"
            ),
        ]
        plan = AdaptationPlan(
            summary=(
                f"{story_bible.main_plot} 建议先生成第 "
                f"{', '.join(str(item) for item in scope)} 章对应的样片段，"
                "让作者确认风格和改编尺度后再继续扩展。"
            ),
            chapter_count=len(chapters),
            recommended_generation_scope=scope,
            rationale=creative_rationale,
            format_rationale=creative_rationale,
            technical_notes=[
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
            "开场需要足够多的可见调查动作，避免依赖旁白解释。",
            "周砚登场要靠阻拦、沉默和走位建立张力，避免纯说明。",
            "解谜场要让观众看见图案和地址如何成形，不能只由角色说出答案。",
            "整理线索的场面容易静态，延展时应加入时间压力或外部打断。",
            "结尾要保留悬疑，不要过度解释下一步。",
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
                    "source_function": scene_plan.get("source_function", ""),
                    "location_id": location_id,
                    "time_of_day": "night",
                    "characters": characters,
                    "purpose": scene_plan["dramatic_purpose"],
                    "scene_purpose": scene_plan["dramatic_purpose"],
                    "conflict": scene_plan.get("conflict")
                    or "A clue demands action while the character fears what it reveals.",
                    "emotional_shift": scene_plan.get("emotional_shift")
                    or "从犹豫到决定继续追查。",
                    "adaptation_reason": scene_plan.get("adaptation_reason", ""),
                    "performance_notes": scene_plan.get("performance_notes", ""),
                    "risk_note": scene_plan.get("risk_note", ""),
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
                        scene_plan.get("adaptation_treatment")
                        or "增加一个可表演动作，把本章的内心怀疑外化出来。"
                    ],
                    "revision_suggestions": [
                        scene_plan.get("risk_note")
                        or "如果场景显得解释感太强，增加阻力或沉默反应。"
                    ],
                    "adaptation_notes": [
                        "把小说叙述压缩为可见动作和短对白。",
                        f"作者选择的风格偏向：{controls.style_focus.value}。",
                    ],
                }
            )
        return {
            "metadata": {
                "title": "雨巷里的来信",
                "source_chapter_count": len(chapters),
                "language": "zh-CN",
                "genre": "悬疑剧情",
                "logline": "年轻档案员林夏沿着父亲留下的信件和旧剧本，追查他失踪背后的真相。",
            },
            "adaptation_profile": controls.model_dump(mode="json"),
            "adaptation_strategy": [
                adaptation_plan.summary,
                "每场戏保留来源章节和改编理由，方便作者追踪取舍。",
                "AI 新增内容单独标记，避免和原文提取混在一起。",
            ],
            "characters": [
                {
                    "id": "char_linxia",
                    "name": "林夏",
                    "role": "主角",
                    "description": "谨慎的年轻档案员，决定继续追查父亲未完成的线索。",
                    "first_appearance_chapter": 1,
                },
                {
                    "id": "char_zhouyan",
                    "name": "周砚",
                    "role": "知情者",
                    "description": "父亲当年的舞台监督，知道旧剧院背后的秘密。",
                    "first_appearance_chapter": 2,
                },
            ],
            "locations": [
                {
                    "id": "loc_archive",
                    "name": "城南档案馆",
                    "description": "雨巷旁的旧档案馆，第一封信在这里被发现。",
                },
                {
                    "id": "loc_theater",
                    "name": "旧剧院",
                    "description": "已经停用的剧院，舞台中央仍亮着一盏灯。",
                },
            ],
            "props": [
                {
                    "id": "prop_letter",
                    "name": "没有编号的信",
                    "description": "疑似父亲留下的神秘信件，引导林夏前往旧剧院。",
                },
                {
                    "id": "prop_script",
                    "name": "旧剧本",
                    "description": "第三幕台词藏着地址的旧剧本。",
                },
            ],
            "scenes": scenes,
            "adaptation_notes": [
                "保留章节间的悬疑线索链。",
                "用场景功能和改编理由帮助作者后续继续打磨。",
            ],
        }

    def _mock_chapter_script_card(
        self,
        chapter: Chapter,
        chapter_card: ChapterCard,
        adaptation_plan: AdaptationPlan,
        controls: AuthorControls,
        feedbacks: list[ScriptFeedback],
    ) -> dict[str, Any]:
        scene_plan = next(
            (
                scene
                for scene in adaptation_plan.scene_plan
                if chapter.index in scene.source_chapters
            ),
            None,
        )
        scene_id = f"sc_{chapter.index:03d}"
        source_excerpt = (
            chapter_card.source_quotes[0].quote
            if chapter_card.source_quotes
            else chapter_card.summary
        )
        location_id = "loc_archive" if chapter.index == 1 else "loc_theater"
        characters = ["char_linxia"] if chapter.index == 1 else ["char_linxia", "char_zhouyan"]
        feedback_notes = [
            item.complaint if not item.desired_change else f"{item.complaint}；希望：{item.desired_change}"
            for item in feedbacks
        ]
        title = scene_plan.title if scene_plan else chapter_card.title
        purpose = (
            scene_plan.dramatic_purpose
            if scene_plan
            else f"把 {chapter_card.title} 的核心事件改成可表演场面。"
        )
        conflict = (
            scene_plan.conflict
            if scene_plan and scene_plan.conflict
            else (chapter_card.conflicts[0] if chapter_card.conflicts else "主角要在犹豫和行动之间做选择。")
        )
        emotional_shift = (
            scene_plan.emotional_shift
            if scene_plan and scene_plan.emotional_shift
            else "从迟疑到决定推进。"
        )
        action_text = (
            f"林夏把“{chapter_card.clues[0] if chapter_card.clues else chapter_card.title}”摆到灯下，"
            f"用实际动作确认这一章的关键线索。"
        )
        if feedback_notes:
            action_text += f" 她停下来，按作者反馈重新处理：{feedback_notes[-1]}"
        dialogue = (
            "这条线索不能只停在心里，我要让它变成下一步行动。"
            if chapter.index == 1
            else "如果你还知道别的，就不要只把答案藏在沉默里。"
        )
        scene = {
            "id": scene_id,
            "title": title,
            "source_chapters": [chapter.index],
            "source_excerpt": source_excerpt[:220],
            "source_function": (
                scene_plan.source_function
                if scene_plan and scene_plan.source_function
                else chapter_card.summary
            ),
            "location_id": location_id,
            "time_of_day": "night",
            "characters": characters,
            "purpose": purpose,
            "scene_purpose": purpose,
            "conflict": conflict,
            "emotional_shift": emotional_shift,
            "adaptation_reason": (
                scene_plan.adaptation_reason
                if scene_plan and scene_plan.adaptation_reason
                else "把章节里的心理和叙述转成观众能看见的行动、停顿和对白。"
            ),
            "performance_notes": (
                scene_plan.performance_notes
                if scene_plan and scene_plan.performance_notes
                else "用物件、走位和沉默反应替代长段解释。"
            ),
            "risk_note": (
                scene_plan.risk_note
                if scene_plan and scene_plan.risk_note
                else "避免让角色直接复述设定，优先保留行动压力。"
            ),
            "production_risk": "如果只解释本章含义，场面会变静态，需要用阻力或道具动作维持节奏。",
            "format_type": controls.format_type.value,
            "actions": [
                {
                    "text": action_text,
                    "beat": "adaptation",
                    "origin": "ai_adapted",
                }
            ],
            "dialogues": [
                {
                    "speaker_id": "char_linxia",
                    "line": dialogue,
                    "emotion": "controlled",
                    "origin": "ai_adapted",
                }
            ],
            "ai_added_content": [
                "增加可见行动，把章节理解卡里的心理判断外化。"
            ],
            "revision_suggestions": [
                "如果作者觉得不忠实，优先检查本场的线索、人物动机和结尾钩子。"
            ],
            "adaptation_notes": [
                f"来源于 {chapter_card.chapter_id} 章节理解卡。",
                *feedback_notes,
            ],
        }
        return ChapterScriptCard(
            chapter_id=chapter_card.chapter_id,
            chapter_index=chapter.index,
            title=chapter_card.title,
            summary=f"{chapter_card.title} 被改成 1 场可表演戏：{purpose}",
            scenes=[scene],
            opening_bridge=(
                "承接上一章的未解线索。"
                if chapter.index > 1
                else "从主角第一次接触核心线索开始。"
            ),
            ending_hook=(
                chapter_card.continuity_notes[0]
                if chapter_card.continuity_notes
                else "留下下一章继续推进的行动钩子。"
            ),
            continuity_links=[
                "合成阶段会检查本章结尾是否自然接到下一章开场。",
                *chapter_card.continuity_notes[:2],
            ],
            absorbed_feedback=feedback_notes,
            revision_notes=[
                "本卡只负责本章剧本化，跨章顺序和过渡在连贯性合成阶段处理。"
            ],
            format_type=controls.format_type,
        ).model_dump(mode="json")

    def _script_from_chapter_script_cards(
        self,
        chapters: list[Chapter],
        script_cards: list[ChapterScriptCard],
        adaptation_plan: AdaptationPlan,
        controls: AuthorControls,
        feedback: ScriptFeedback | None,
    ) -> dict[str, Any]:
        scenes = [
            scene.model_dump(mode="json")
            for card in sorted(script_cards, key=lambda item: item.chapter_index)
            for scene in card.scenes
        ]
        scenes, characters, locations = self._normalize_script_references(scenes)
        feedback_note = (
            f"本次合成已吸收作者最终反馈：{feedback.complaint}"
            if feedback
            else "本次合成基于作者已通过的逐章剧本卡。"
        )
        return {
            "metadata": {
                "title": "逐章合成剧本初稿",
                "source_chapter_count": len(chapters),
                "language": "zh-CN",
                "genre": "悬疑剧情",
                "logline": "主角沿着章节线索逐步追查真相，每章剧本卡被合成为连续可拍段落。",
            },
            "adaptation_profile": controls.model_dump(mode="json"),
            "adaptation_strategy": [
                adaptation_plan.summary,
                "最终剧本只来自已通过的章节剧本卡，不从简介卡直接发散。",
                "连贯性合成只调整过渡、节奏提示和衔接说明，不擅自推翻已通过章节核心剧情。",
                feedback_note,
            ],
            "characters": characters,
            "locations": locations,
            "props": [
                {
                    "id": "prop_letter",
                    "name": "没有编号的信",
                    "description": "推动主角开始追查的信件。",
                },
                {
                    "id": "prop_script",
                    "name": "旧剧本",
                    "description": "把文本线索转成可见解谜动作的道具。",
                },
            ],
            "scenes": scenes,
            "adaptation_notes": [
                feedback_note,
                "每场戏保留来源章节、原文功能、改编理由和可继续打磨建议。",
            ],
        }

    def _normalize_script_references(
        self,
        scenes: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        characters: dict[str, dict[str, Any]] = {
            "char_linxia": {
                "id": "char_linxia",
                "name": "林夏",
                "role": "主角",
                "description": "谨慎但逐渐主动的追查者，把父亲留下的线索变成行动。",
                "first_appearance_chapter": 1,
            },
            "char_zhouyan": {
                "id": "char_zhouyan",
                "name": "周砚",
                "role": "知情者",
                "description": "与旧剧院和父亲过去有关的知情者，推动主角接近真相。",
                "first_appearance_chapter": 2,
            },
        }
        locations: dict[str, dict[str, Any]] = {
            "loc_archive": {
                "id": "loc_archive",
                "name": "城南档案馆",
                "description": "主角发现第一条线索的旧档案空间。",
            },
            "loc_theater": {
                "id": "loc_theater",
                "name": "旧剧院",
                "description": "承载父亲过去和线索链的核心场景。",
            },
            "loc_clocktower": {
                "id": "loc_clocktower",
                "name": "城北钟楼",
                "description": "多条线索汇合、制造下一步悬念的地点。",
            },
        }
        character_aliases = {
            "林夏": "char_linxia",
            "char_林夏": "char_linxia",
            "char_lin_xia": "char_linxia",
            "char_linxia": "char_linxia",
            "周砚": "char_zhouyan",
            "char_周砚": "char_zhouyan",
            "char_zhou_yan": "char_zhouyan",
            "char_zhouyan": "char_zhouyan",
            "母亲": "char_mother",
            "char_母亲": "char_mother",
            "char_mother": "char_mother",
            "char_muqin": "char_mother",
            "父亲": "char_father",
            "char_父亲": "char_father",
            "char_father": "char_father",
            "char_fuqin": "char_father",
        }
        location_aliases = {
            "城南档案馆": "loc_archive",
            "loc_城南档案馆": "loc_archive",
            "旧剧院": "loc_theater",
            "loc_旧剧院": "loc_theater",
            "loc_old_theater": "loc_theater",
            "loc_jiujuyuan": "loc_theater",
            "城北钟楼": "loc_clocktower",
            "loc_城北钟楼": "loc_clocktower",
            "loc_clock_tower": "loc_clocktower",
            "loc_clocktower": "loc_clocktower",
            "loc_zhonglou": "loc_clocktower",
            "林夏家": "loc_home",
            "loc_林夏家": "loc_home",
            "loc_home": "loc_home",
        }
        character_names = {
            "char_mother": "母亲",
            "char_father": "父亲",
        }
        location_names = {
            "loc_home": "林夏家",
        }
        for scene in scenes:
            source_chapter = min(scene.get("source_chapters") or [1])
            location_id = self._canonical_reference_id(
                str(scene.get("location_id") or "loc_archive"),
                location_aliases,
            )
            scene["location_id"] = location_id
            if location_id not in locations:
                locations[location_id] = {
                    "id": location_id,
                    "name": location_names.get(location_id, self._fallback_reference_name(location_id, "地点")),
                    "description": "来自已通过章节剧本卡的场景地点。",
                }
            scene_characters = [
                self._canonical_reference_id(str(character_id), character_aliases)
                for character_id in scene.get("characters", [])
            ]
            for dialogue in scene.get("dialogues", []):
                speaker_id = self._canonical_reference_id(
                    str(dialogue.get("speaker_id") or "char_linxia"),
                    character_aliases,
                )
                dialogue["speaker_id"] = speaker_id
                scene_characters.append(speaker_id)
            if not scene_characters:
                scene_characters.append("char_linxia")
            normalized_characters = []
            for character_id in scene_characters:
                if character_id not in normalized_characters:
                    normalized_characters.append(character_id)
                if character_id not in characters:
                    characters[character_id] = {
                        "id": character_id,
                        "name": character_names.get(
                            character_id,
                            self._fallback_reference_name(character_id, "角色"),
                        ),
                        "role": "角色",
                        "description": "来自已通过章节剧本卡的对白或行动角色。",
                        "first_appearance_chapter": source_chapter,
                    }
            scene["characters"] = normalized_characters
        return scenes, list(characters.values()), list(locations.values())

    def _normalize_chapter_script_card_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        next_payload = {**payload}
        scenes = [
            {**scene, "dialogues": [dict(dialogue) for dialogue in scene.get("dialogues", [])]}
            for scene in next_payload.get("scenes", []) or []
            if isinstance(scene, dict)
        ]
        for index, scene in enumerate(scenes, start=1):
            scene_id = str(scene.get("id") or "")
            if not re.fullmatch(r"sc_[0-9]{3}", scene_id):
                chapter_index = int(next_payload.get("chapter_index") or 1)
                scene["id"] = f"sc_{chapter_index if len(scenes) == 1 else chapter_index * 10 + index:03d}"
        normalized_scenes, _, _ = self._normalize_script_references(scenes)
        next_payload["scenes"] = normalized_scenes
        return next_payload

    def _normalize_planner_output_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        next_payload = {**payload}
        scenes: list[dict[str, Any]] = []
        for index, raw_scene in enumerate(next_payload.get("scenes", []) or [], start=1):
            if not isinstance(raw_scene, dict):
                continue
            scene = {**raw_scene}
            scene_id = str(scene.get("id") or "")
            if not re.fullmatch(r"sc_[0-9]{3}", scene_id):
                scene["id"] = f"sc_{index:03d}"
            scene["title"] = self._stringify_llm_value(scene.get("title") or f"场景 {index}")
            scene["dramatic_purpose"] = self._stringify_llm_value(
                scene.get("dramatic_purpose")
                or scene.get("source_function")
                or scene.get("title")
                or "把本章核心事件转成可表演场面。"
            )
            for key in (
                "conflict",
                "emotional_shift",
                "source_excerpt",
                "source_function",
                "adaptation_treatment",
                "adaptation_reason",
                "performance_notes",
                "risk_note",
            ):
                scene[key] = self._stringify_llm_value(scene.get(key) or "")
            scene["key_events"] = [
                self._stringify_llm_value(item)
                for item in scene.get("key_events", []) or []
            ]
            scenes.append(scene)
        next_payload["scenes"] = scenes
        return next_payload

    @staticmethod
    def _stringify_llm_value(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            preferred = [
                value.get(key)
                for key in ("quote", "text", "summary", "reason", "description", "value")
                if value.get(key)
            ]
            if preferred:
                return "；".join(AdaptationWorkflow._stringify_llm_value(item) for item in preferred)
            return "；".join(
                f"{key}: {AdaptationWorkflow._stringify_llm_value(item)}"
                for key, item in value.items()
            )
        if isinstance(value, list):
            return "；".join(AdaptationWorkflow._stringify_llm_value(item) for item in value)
        return str(value)

    @staticmethod
    def _canonical_reference_id(value: str, aliases: dict[str, str]) -> str:
        canonical = aliases.get(value)
        if canonical:
            return canonical
        expected_prefix = next(
            (
                prefix
                for prefix in ("char", "loc", "prop")
                if aliases and all(item.startswith(f"{prefix}_") for item in aliases.values())
            ),
            None,
        )
        if expected_prefix is None:
            return value
        if re.fullmatch(rf"{expected_prefix}_[a-zA-Z0-9_]+", value):
            return value
        raw_value = value.split("_", 1)[1] if value.startswith(f"{expected_prefix}_") else value
        slug = re.sub(r"[^a-zA-Z0-9_]+", "_", raw_value).strip("_").lower()
        return f"{expected_prefix}_{slug or 'unknown'}"

    @staticmethod
    def _fallback_reference_name(value: str, fallback: str) -> str:
        stripped = value.split("_", 1)[1] if "_" in value else value
        return stripped.replace("_", " ").strip() or fallback

    def _remote_reader_output(self, chapters: list[Chapter]) -> dict[str, Any]:
        return self._remote_json(
            "Extract characters, locations, events, and props. Return JSON only matching the provided ReaderOutput schema.",
            {
                "schema": ReaderOutput.model_json_schema(),
                "chapters": [chapter.model_dump() for chapter in chapters],
            },
        )

    def _remote_chapter_card(
        self,
        chapter: Chapter,
        feedback_notes: str | None = None,
    ) -> dict[str, Any]:
        return self._remote_json(
            (
                "你是小说改编副编剧。请把一个完整章节作为最小语义单元阅读，"
                "返回严格匹配 ChapterCard schema 的 JSON。所有可展示给作者的字段必须使用简体中文。"
                "保留本章真实含义，不要编造本章没有支持的人物、线索或事件。"
                "如果 payload 中有 author_feedback_notes，必须优先用它校正本章理解，"
                "并在 adaptation_opportunities 或 continuity_notes 中说明吸收了哪些反馈。"
            ),
            {
                "schema": ChapterCard.model_json_schema(),
                "chapter": chapter.model_dump(mode="json"),
                "chapter_id": f"ch_{chapter.index:03d}",
                "author_feedback_notes": feedback_notes or "",
            },
        )

    def _remote_chapter_script_card(
        self,
        chapter: Chapter,
        chapter_card: ChapterCard,
        adaptation_plan: AdaptationPlan,
        author_controls: AuthorControls,
        feedbacks: list[ScriptFeedback],
    ) -> dict[str, Any]:
        return self._remote_json(
            (
                "你是小说改编副编剧。请只把当前这一章改成 ChapterScriptCard。"
                "返回严格匹配 ChapterScriptCard schema 的 JSON。所有展示给作者的字段必须使用简体中文。"
                "不要直接生成最终 YAML，不要改写其他章节。每张卡至少包含一场戏，并说明 opening_bridge、"
                "ending_hook、continuity_links 和 absorbed_feedback。若有作者反馈，必须明确吸收。"
            ),
            {
                "schema": ChapterScriptCard.model_json_schema(),
                "chapter": chapter.model_dump(mode="json"),
                "chapter_card": chapter_card.model_dump(mode="json"),
                "adaptation_plan": adaptation_plan.model_dump(mode="json"),
                "author_controls": author_controls.model_dump(mode="json"),
                "feedback": [item.model_dump(mode="json") for item in feedbacks],
            },
        )

    def _remote_story_bible(self, chapter_cards: list[dict[str, Any]]) -> dict[str, Any]:
        return self._remote_json(
            (
                "你是小说改编副编剧。请根据逐章理解卡综合一份全书 Story Bible，"
                "返回严格匹配 StoryBible schema 的 JSON。所有可展示给作者的字段必须使用简体中文。"
                "推荐一个小的生成范围，通常先选前三章，不要建议一次生成全书剧本。"
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
                "你是小说改编副编剧。请为 Story Bible 推荐的生成范围创建剧本分场计划，"
                "返回严格匹配 PlannerOutput schema 的 JSON。所有可展示给作者的字段必须使用简体中文，"
                "不要把 short_drama、psychological、balanced 这类枚举当成作者说明。"
                "每场必须引用来源章节，并基于章节理解卡证据说明："
                "source_function=原文这一章/段落在故事中的功能；"
                "adaptation_treatment=准备如何把它改成动作、对白、场景或冲突；"
                "adaptation_reason=为什么这样改，而不是解释系统流程；"
                "performance_notes=演员、镜头、舞台或声音如何表现；"
                "risk_note=作者后续打磨时要避免的问题。"
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
                "你是小说改编副编剧。请生成严格匹配 ScriptJson schema 的剧本 JSON。"
                "所有可展示给作者的字段必须使用简体中文。只使用分场计划、章节理解卡、"
                "Story Bible 和作者控制项，不要编造无证据的主线。每场戏需要保留来源章节、"
                "原文功能、改编理由、表演提示和风险提示；AI 新增内容必须单独标记。"
                "返回 JSON only。"
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
    script_card_count = len(state.get("chapter_script_cards") or [])
    lines = [
        "# 改编报告",
        "",
        f"- 校验通过: `{report.valid}`",
        f"- 校验摘要: {report.summary}",
        f"- 是否自动修复过: `{state.get('repaired', False)}`",
        f"- 剧本类型: {_format_label(controls.format_type.value)}",
        f"- 改编尺度: {_scale_label(controls.adaptation_scale.value)}",
        f"- 风格偏向: {_style_label(controls.style_focus.value)}",
        "",
        "## 改编策略",
        "",
        plan.summary,
        "",
        "## 长文本处理",
        "",
        f"- Story Bible 主线: {story_bible.main_plot}",
        f"- 推荐生成范围: 第 {', '.join(str(item) for item in plan.recommended_generation_scope)} 章",
        f"- 使用章节理解卡: `{len(story_bible.chapter_index)}` 张",
        f"- 使用章节剧本卡: `{script_card_count}` 张",
        *[f"- {item}" for item in plan.technical_notes],
        "",
        "## 校验问题",
        "",
    ]
    if not report.issues:
        lines.append("没有发现校验问题。")
    else:
        for issue in report.issues:
            lines.append(f"- **{issue.severity.value}** `{issue.path}`: {issue.message}")
            if issue.suggestion:
                lines.append(f"  建议: {issue.suggestion}")
    return "\n".join(lines) + "\n"


def _continuity_report_markdown(
    script_cards: list[ChapterScriptCard],
    feedback: ScriptFeedback | None,
) -> str:
    lines = [
        "# 连贯性合成报告",
        "",
        "## 合成原则",
        "",
        "- 只使用作者已通过的章节剧本卡作为剧本来源。",
        "- 合成阶段重点检查章节之间的开场承接、结尾钩子、人物动机和线索连续性。",
        "- 不擅自推翻单章已通过的核心剧情；如果要改某章，先回到章节剧本卡重写。",
        "",
        "## 已合成章节",
        "",
    ]
    for card in sorted(script_cards, key=lambda item: item.chapter_index):
        lines.append(f"- `{card.chapter_id}` {card.title}: {card.opening_bridge} -> {card.ending_hook}")
    if feedback:
        lines.extend(
            [
                "",
                "## 本次返修反馈",
                "",
                f"- 类型: `{feedback.target_type}`",
                f"- 作者不满意点: {feedback.complaint}",
                f"- 希望调整: {feedback.desired_change or '未填写'}",
                f"- AI 判断: {feedback.ai_assessment}",
            ]
        )
    return "\n".join(lines) + "\n"


def _plan_markdown(plan_payload: dict[str, Any]) -> str:
    plan = AdaptationPlan.model_validate(plan_payload)
    lines = [
        "# 改编计划",
        "",
        f"- 章节数: `{plan.chapter_count}`",
        f"- 推荐剧本类型: {_format_label(plan.recommended_format_type.value)}",
        f"- 推荐风格: {_style_label(plan.recommended_style_focus.value)}",
        f"- 推荐尺度: {_scale_label(plan.recommended_adaptation_scale.value)}",
        f"- 推荐生成范围: 第 {', '.join(str(item) for item in plan.recommended_generation_scope)} 章",
        "",
        "## 我理解的故事",
        "",
        plan.summary,
        "",
        "## 为什么推荐这个方向",
        "",
    ]
    lines.extend(f"- {item}" for item in (plan.format_rationale or plan.rationale))
    lines.extend(["", "## 主要人物和关系", ""])
    lines.extend(f"- {item}" for item in plan.character_notes)
    lines.extend(["", "## 分章改编理由", ""])
    for scene in plan.scene_plan:
        lines.append(f"### `{scene.id}` {scene.title}")
        lines.append("")
        lines.append(f"- 来源章节: 第 {', '.join(str(item) for item in scene.source_chapters)} 章")
        lines.append(f"- 原文功能: {scene.source_function or scene.dramatic_purpose}")
        lines.append(f"- 改编处理: {scene.adaptation_treatment or scene.dramatic_purpose}")
        lines.append(f"- 为什么这样改: {scene.adaptation_reason or scene.dramatic_purpose}")
        if scene.performance_notes:
            lines.append(f"- 表演化提示: {scene.performance_notes}")
        if scene.conflict:
            lines.append(f"- 核心冲突: {scene.conflict}")
        if scene.emotional_shift:
            lines.append(f"- 情绪变化: {scene.emotional_shift}")
        if scene.risk_note:
            lines.append(f"- 风险提醒: {scene.risk_note}")
        lines.append("")
    lines.extend(["## 长文本处理说明", ""])
    lines.extend(f"- {item}" for item in plan.technical_notes)
    lines.extend(["", "## 风险提醒", ""])
    for risk in plan.risks:
        lines.append(f"- **{risk.severity}** {risk.target}: {risk.message}")
        lines.append(f"  建议: {risk.suggestion}")
    return "\n".join(lines).rstrip() + "\n"


SCRIPT_FORMAT_LABELS = {
    "film": "影视剧本",
    "short_drama": "短剧",
    "stage_play": "舞台剧",
    "radio_drama": "广播剧",
    "animation": "动画",
    "game_script": "游戏脚本",
}

STYLE_FOCUS_LABELS = {
    "psychological": "心理外化",
    "action": "动作推进",
    "dialogue": "对白强化",
    "suspense": "悬疑节奏",
    "relationship": "关系冲突",
    "custom": "自定义",
}

ADAPTATION_SCALE_LABELS = {
    "faithful": "忠实改编",
    "balanced": "平衡改编",
    "bold": "大胆改编",
}


def _format_label(value: str) -> str:
    return SCRIPT_FORMAT_LABELS.get(value, value)


def _style_label(value: str) -> str:
    return STYLE_FOCUS_LABELS.get(value, value)


def _scale_label(value: str) -> str:
    return ADAPTATION_SCALE_LABELS.get(value, value)


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
