from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ScriptMetadata(StrictBaseModel):
    title: str = Field(..., min_length=1, description="Script title.")
    source_chapter_count: int = Field(..., ge=3, description="Number of source chapters.")
    language: str = Field(default="zh-CN", description="Primary script language.")
    genre: str = Field(default="drama", description="Broad genre label.")
    logline: str = Field(..., min_length=1, description="One-sentence story premise.")


class ScriptFormat(str, Enum):
    film = "film"
    short_drama = "short_drama"
    stage_play = "stage_play"
    radio_drama = "radio_drama"
    animation = "animation"
    game_script = "game_script"


class AdaptationScale(str, Enum):
    faithful = "faithful"
    balanced = "balanced"
    bold = "bold"


class StyleFocus(str, Enum):
    psychological = "psychological"
    action = "action"
    dialogue = "dialogue"
    suspense = "suspense"
    relationship = "relationship"
    custom = "custom"


class ContentOrigin(str, Enum):
    source_extracted = "source_extracted"
    ai_adapted = "ai_adapted"
    ai_added = "ai_added"


class AuthorControls(StrictBaseModel):
    format_type: ScriptFormat = ScriptFormat.short_drama
    adaptation_scale: AdaptationScale = AdaptationScale.balanced
    style_focus: StyleFocus = StyleFocus.psychological
    preserve_items: list[str] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    author_notes: str | None = None


class Character(StrictBaseModel):
    id: str = Field(..., pattern=r"^char_[a-zA-Z0-9_]+$")
    name: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    first_appearance_chapter: int = Field(..., ge=1)


class Location(StrictBaseModel):
    id: str = Field(..., pattern=r"^loc_[a-zA-Z0-9_]+$")
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)


class Prop(StrictBaseModel):
    id: str = Field(..., pattern=r"^prop_[a-zA-Z0-9_]+$")
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)


class ActionCue(StrictBaseModel):
    text: str = Field(..., min_length=1)
    beat: str = Field(default="action", min_length=1)
    origin: ContentOrigin = ContentOrigin.ai_adapted


class DialogueLine(StrictBaseModel):
    speaker_id: str = Field(..., pattern=r"^char_[a-zA-Z0-9_]+$")
    line: str = Field(..., min_length=1)
    emotion: str | None = None
    origin: ContentOrigin = ContentOrigin.ai_adapted


class Scene(StrictBaseModel):
    id: str = Field(..., pattern=r"^sc_[0-9]{3}$")
    title: str = Field(..., min_length=1)
    source_chapters: list[int] = Field(..., min_length=1)
    source_excerpt: str = Field(..., min_length=1)
    source_function: str = Field(
        default="",
        description="What the source chapter or passage does in the original story.",
    )
    location_id: str = Field(..., pattern=r"^loc_[a-zA-Z0-9_]+$")
    time_of_day: str = Field(default="unspecified")
    characters: list[str] = Field(..., min_length=1)
    purpose: str = Field(..., min_length=1)
    scene_purpose: str = Field(..., min_length=1)
    conflict: str = Field(..., min_length=1)
    emotional_shift: str = Field(..., min_length=1)
    adaptation_reason: str = Field(
        default="",
        description="Why this adaptation choice helps the scene become playable.",
    )
    performance_notes: str = Field(
        default="",
        description="How actors, camera, staging, or sound can externalize the prose.",
    )
    risk_note: str = Field(
        default="",
        description="Specific creative risk to watch when revising this scene.",
    )
    production_risk: str = Field(..., min_length=1)
    format_type: ScriptFormat = ScriptFormat.short_drama
    actions: list[ActionCue] = Field(default_factory=list)
    dialogues: list[DialogueLine] = Field(default_factory=list)
    ai_added_content: list[str] = Field(default_factory=list)
    revision_suggestions: list[str] = Field(default_factory=list)
    adaptation_notes: list[str] = Field(default_factory=list)


class ScriptJson(StrictBaseModel):
    metadata: ScriptMetadata
    adaptation_profile: AuthorControls = Field(default_factory=AuthorControls)
    adaptation_strategy: list[str] = Field(default_factory=list)
    characters: list[Character] = Field(..., min_length=1)
    locations: list[Location] = Field(..., min_length=1)
    props: list[Prop] = Field(default_factory=list)
    scenes: list[Scene] = Field(..., min_length=1)
    adaptation_notes: list[str] = Field(default_factory=list)


class Chapter(StrictBaseModel):
    index: int = Field(..., ge=1)
    title: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    char_count: int = Field(..., ge=1)


class StoryFact(StrictBaseModel):
    kind: Literal["character", "location", "event", "prop"]
    name: str
    description: str
    source_chapter: int = Field(..., ge=1)


class ReaderOutput(StrictBaseModel):
    facts: list[StoryFact] = Field(..., min_length=1)


class SourceQuote(StrictBaseModel):
    quote: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    confidence: Literal["high", "medium", "low"] = "medium"


class ChapterCard(StrictBaseModel):
    chapter_id: str = Field(..., pattern=r"^ch_[0-9]{3}$")
    chapter_index: int = Field(..., ge=1)
    title: str = Field(..., min_length=1)
    char_count: int = Field(..., ge=1)
    summary: str = Field(..., min_length=1)
    key_events: list[str] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    emotional_beats: list[str] = Field(default_factory=list)
    clues: list[str] = Field(default_factory=list)
    adaptation_opportunities: list[str] = Field(default_factory=list)
    source_quotes: list[SourceQuote] = Field(default_factory=list)
    continuity_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def chapter_id_matches_index(self):
        expected = f"ch_{self.chapter_index:03d}"
        if self.chapter_id != expected:
            raise ValueError(f"chapter_id must be {expected} for chapter_index {self.chapter_index}.")
        return self


class StoryBibleChapter(StrictBaseModel):
    chapter_id: str = Field(..., pattern=r"^ch_[0-9]{3}$")
    title: str = Field(..., min_length=1)
    char_count: int = Field(..., ge=1)
    summary: str = Field(..., min_length=1)


class StoryBible(StrictBaseModel):
    main_plot: str = Field(..., min_length=1)
    character_arcs: list[str] = Field(default_factory=list)
    relationship_map: list[str] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)
    major_clues: list[str] = Field(default_factory=list)
    adaptation_risks: list[str] = Field(default_factory=list)
    chapter_index: list[StoryBibleChapter] = Field(..., min_length=1)
    recommended_generation_scope: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def scope_is_valid(self):
        valid_indexes = {
            int(chapter.chapter_id.removeprefix("ch_")) for chapter in self.chapter_index
        }
        if len(self.recommended_generation_scope) != len(set(self.recommended_generation_scope)):
            raise ValueError("recommended_generation_scope must not contain duplicates.")
        unknown = [
            item for item in self.recommended_generation_scope if item not in valid_indexes
        ]
        if unknown:
            raise ValueError(f"recommended_generation_scope contains unknown chapters: {unknown}.")
        return self


class ScenePlan(StrictBaseModel):
    id: str = Field(..., pattern=r"^sc_[0-9]{3}$")
    title: str
    source_chapters: list[int]
    dramatic_purpose: str
    key_events: list[str] = Field(default_factory=list)
    conflict: str = ""
    emotional_shift: str = ""
    source_excerpt: str = ""
    source_function: str = ""
    adaptation_treatment: str = ""
    adaptation_reason: str = ""
    performance_notes: str = ""
    risk_note: str = ""


class PlannerOutput(StrictBaseModel):
    scenes: list[ScenePlan] = Field(..., min_length=1)


class AdaptationRisk(StrictBaseModel):
    severity: Literal["info", "warning", "error"] = "warning"
    target: str
    message: str
    suggestion: str


class AdaptationPlan(StrictBaseModel):
    summary: str
    chapter_count: int = Field(..., ge=3)
    recommended_format_type: ScriptFormat = ScriptFormat.short_drama
    recommended_style_focus: StyleFocus = StyleFocus.psychological
    recommended_adaptation_scale: AdaptationScale = AdaptationScale.balanced
    recommended_generation_scope: list[int] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    format_rationale: list[str] = Field(default_factory=list)
    technical_notes: list[str] = Field(default_factory=list)
    character_notes: list[str] = Field(default_factory=list)
    plot_threads: list[str] = Field(default_factory=list)
    scene_plan: list[ScenePlan] = Field(default_factory=list)
    risks: list[AdaptationRisk] = Field(default_factory=list)


class IssueSeverity(str, Enum):
    info = "info"
    warning = "warning"
    error = "error"


class ValidationIssue(StrictBaseModel):
    severity: IssueSeverity
    path: str
    message: str
    suggestion: str | None = None


class ValidationReport(StrictBaseModel):
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    summary: str


class RunStatus(str, Enum):
    queued = "queued"
    running = "running"
    planned = "planned"
    validating = "validating"
    repairing = "repairing"
    exporting = "exporting"
    succeeded = "succeeded"
    failed_validation = "failed_validation"
    failed_llm = "failed_llm"
    failed_internal = "failed_internal"


class RunStage(StrictBaseModel):
    name: str
    status: Literal["pending", "running", "succeeded", "failed"] = "pending"
    message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class RunManifest(StrictBaseModel):
    run_id: str
    status: RunStatus
    current_stage: str | None = None
    stages: list[RunStage] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    error: str | None = None
    created_at: str
    updated_at: str


class CreateRunResponse(StrictBaseModel):
    run_id: str
    status: RunStatus


class RunStatusResponse(StrictBaseModel):
    run_id: str
    status: RunStatus
    current_stage: str | None
    stages: list[RunStage]
    artifacts: list[str]
    error: str | None = None


class YamlValidationRequest(StrictBaseModel):
    yaml_text: str = Field(..., min_length=1)


class YamlValidationResponse(StrictBaseModel):
    report: ValidationReport


class GenerateRunRequest(StrictBaseModel):
    controls: AuthorControls = Field(default_factory=AuthorControls)


class LlmStatusResponse(StrictBaseModel):
    mode: Literal["mock", "real"]
    use_mock_llm: bool
    api_key_configured: bool
    base_url_configured: bool
    model: str


class LlmTestResponse(LlmStatusResponse):
    success: bool
    message: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def script_json_schema() -> dict[str, Any]:
    return ScriptJson.model_json_schema()
