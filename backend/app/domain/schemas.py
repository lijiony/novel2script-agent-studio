from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ScriptMetadata(StrictBaseModel):
    title: str = Field(..., min_length=1, description="Script title.")
    source_chapter_count: int = Field(..., ge=3, description="Number of source chapters.")
    language: str = Field(default="zh-CN", description="Primary script language.")
    genre: str = Field(default="drama", description="Broad genre label.")
    logline: str = Field(..., min_length=1, description="One-sentence story premise.")


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


class DialogueLine(StrictBaseModel):
    speaker_id: str = Field(..., pattern=r"^char_[a-zA-Z0-9_]+$")
    line: str = Field(..., min_length=1)
    emotion: str | None = None


class Scene(StrictBaseModel):
    id: str = Field(..., pattern=r"^sc_[0-9]{3}$")
    title: str = Field(..., min_length=1)
    source_chapters: list[int] = Field(..., min_length=1)
    location_id: str = Field(..., pattern=r"^loc_[a-zA-Z0-9_]+$")
    time_of_day: str = Field(default="unspecified")
    characters: list[str] = Field(..., min_length=1)
    purpose: str = Field(..., min_length=1)
    actions: list[ActionCue] = Field(default_factory=list)
    dialogues: list[DialogueLine] = Field(default_factory=list)
    adaptation_notes: list[str] = Field(default_factory=list)


class ScriptJson(StrictBaseModel):
    metadata: ScriptMetadata
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


class ScenePlan(StrictBaseModel):
    id: str = Field(..., pattern=r"^sc_[0-9]{3}$")
    title: str
    source_chapters: list[int]
    dramatic_purpose: str
    key_events: list[str] = Field(default_factory=list)


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


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def script_json_schema() -> dict[str, Any]:
    return ScriptJson.model_json_schema()
