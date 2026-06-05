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

The schema is designed for an AI adaptation co-writer, not only a YAML formatter.
It stores the script draft plus adaptation reasoning: author controls, strategy,
scene purpose, conflict, emotional shift, source excerpt, AI-added content,
revision suggestions, production risk, and content origin markers. This lets an
author see what came from the source, what the AI adapted, what the AI added, and
what should be polished next.

The LLM outputs structured JSON first; the application validates it and exports
YAML after validation.
"""
