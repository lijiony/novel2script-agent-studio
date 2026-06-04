from app.domain.schemas import ScriptJson


def schema_markdown() -> str:
    fields = ScriptJson.model_fields
    rows = "\n".join(
        f"| `{name}` | {field.annotation!s} | {field.description or ''} |"
        for name, field in fields.items()
    )
    return f"""# Script YAML Schema

This document is generated from the Pydantic v2 `ScriptJson` model used by the backend.

## Top-level Fields

| Field | Type | Description |
|---|---|---|
{rows}

## Design Reason

The schema separates metadata, reusable entities, scenes, actions, dialogues, and adaptation notes so authors can edit the script draft without losing structure. The LLM outputs structured JSON first; the application validates it and exports YAML after validation.
"""
