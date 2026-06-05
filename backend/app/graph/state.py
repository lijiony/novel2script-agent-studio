from typing import Any, TypedDict


class WorkflowState(TypedDict, total=False):
    run_id: str
    input_text: str
    chapters: list[dict[str, Any]]
    chapter_cards: list[dict[str, Any]]
    reader_output: dict[str, Any]
    story_bible: dict[str, Any]
    planner_output: dict[str, Any]
    adaptation_plan: dict[str, Any]
    author_controls: dict[str, Any]
    script_json: dict[str, Any]
    validation_report: dict[str, Any]
    repaired: bool
    yaml_text: str
    report_markdown: str
    error: str
