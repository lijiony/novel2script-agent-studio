from collections import Counter
from typing import Any
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from ruamel.yaml import YAML

from app.domain.schemas import (
    IssueSeverity,
    ScriptJson,
    ValidationIssue,
    ValidationReport,
    script_json_schema,
)


def validate_script_payload(payload: dict[str, Any]) -> ValidationReport:
    issues: list[ValidationIssue] = []

    schema_validator = Draft202012Validator(script_json_schema())
    for error in sorted(schema_validator.iter_errors(payload), key=str):
        path = ".".join(str(part) for part in error.absolute_path) or "$"
        issues.append(
            ValidationIssue(
                severity=IssueSeverity.error,
                path=path,
                message=error.message,
                suggestion="Update the field so it matches the generated JSON Schema.",
            )
        )

    try:
        script = ScriptJson.model_validate(payload)
    except ValidationError as exc:
        for error in exc.errors():
            path = ".".join(str(part) for part in error["loc"]) or "$"
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.error,
                    path=path,
                    message=str(error["msg"]),
                    suggestion="Fix the typed field value.",
                )
            )
        return _report(issues)

    issues.extend(_semantic_issues(script))
    return _report(issues)


def validate_yaml_text(yaml_text: str) -> ValidationReport:
    yaml = YAML(typ="safe")
    try:
        payload = yaml.load(yaml_text)
    except Exception as exc:  # pragma: no cover - exact parser errors vary
        return ValidationReport(
            valid=False,
            summary="YAML parsing failed.",
            issues=[
                ValidationIssue(
                    severity=IssueSeverity.error,
                    path="$",
                    message=str(exc),
                    suggestion="Fix YAML indentation or scalar syntax.",
                )
            ],
        )
    if not isinstance(payload, dict):
        return ValidationReport(
            valid=False,
            summary="YAML root must be an object.",
            issues=[
                ValidationIssue(
                    severity=IssueSeverity.error,
                    path="$",
                    message="YAML root is not a mapping object.",
                )
            ],
        )
    return validate_script_payload(payload)


def _semantic_issues(script: ScriptJson) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    character_ids = {character.id for character in script.characters}
    location_ids = {location.id for location in script.locations}
    scene_ids = [scene.id for scene in script.scenes]

    for scene_id, count in Counter(scene_ids).items():
        if count > 1:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.error,
                    path="scenes",
                    message=f"Duplicate scene id '{scene_id}'.",
                    suggestion="Use stable unique scene ids such as sc_001.",
                )
            )

    represented_chapters: set[int] = set()
    for scene_index, scene in enumerate(script.scenes):
        scene_path = f"scenes.{scene_index}"
        represented_chapters.update(scene.source_chapters)

        if scene.location_id not in location_ids:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.error,
                    path=f"{scene_path}.location_id",
                    message=f"Unknown location id '{scene.location_id}'.",
                )
            )

        for character_id in scene.characters:
            if character_id not in character_ids:
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.error,
                        path=f"{scene_path}.characters",
                        message=f"Unknown character id '{character_id}'.",
                    )
                )

        for dialogue_index, dialogue in enumerate(scene.dialogues):
            if dialogue.speaker_id not in character_ids:
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.error,
                        path=f"{scene_path}.dialogues.{dialogue_index}.speaker_id",
                        message=f"Unknown speaker id '{dialogue.speaker_id}'.",
                    )
                )

        if not scene.actions and not scene.dialogues:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.warning,
                    path=scene_path,
                    message="Scene has neither actions nor dialogues.",
                    suggestion="Add at least one visual cue or spoken line.",
                )
            )

    if len(represented_chapters) < min(3, script.metadata.source_chapter_count):
        issues.append(
            ValidationIssue(
                severity=IssueSeverity.error,
                path="scenes.source_chapters",
                message="Scenes do not cover at least 3 source chapters.",
                suggestion="Add scene references for each source chapter.",
            )
        )

    return issues


def _report(issues: list[ValidationIssue]) -> ValidationReport:
    has_errors = any(issue.severity == IssueSeverity.error for issue in issues)
    if has_errors:
        summary = f"Validation failed with {len(issues)} issue(s)."
    elif issues:
        summary = f"Validation passed with {len(issues)} warning(s)."
    else:
        summary = "Validation passed with no issues."
    return ValidationReport(valid=not has_errors, issues=issues, summary=summary)
