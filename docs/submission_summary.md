# Submission Summary

Use this page when filling the XEngineer submission form.

## Topic

AI 小说转剧本工具

## Repository

```text
https://github.com/lijiony/novel2script-agent-studio
```

## Demo Video

```text
TODO: replace with the narrated demo video URL after upload.
```

## Short Project Summary

Novel2Script Agent Studio is a lightweight AI workbench that converts three or more chapters of novel text into an editable screenplay YAML draft. It uses a fixed LangGraph workflow to parse chapters, extract story facts, plan scenes, generate structured script JSON, validate the result with Pydantic and JSON Schema, export YAML with `ruamel.yaml`, and generate an adaptation report. The frontend provides a Next.js workbench with a Monaco YAML editor, validation feedback, and artifact downloads.

## Core Requirement Mapping

| Requirement | Implementation |
|---|---|
| Accept 3+ chapters of novel text | Paste/upload `.txt`; backend rejects fewer than three chapters |
| Convert novel to structured script | LangGraph pipeline generates structured `script.json` |
| Output YAML | Validated JSON is exported to `script.yaml` with `ruamel.yaml` |
| Editable draft | Browser YAML editor supports edits and backend revalidation |
| YAML Schema document | `docs/schema.md`, generated `schema.json`, and per-run `schema.md` |
| Explain schema design | Schema design goals are documented in `docs/schema.md` |

## Original Work

- Product workflow and UX design.
- Pydantic screenplay schema and semantic validator.
- Fixed LangGraph adaptation pipeline.
- Run artifact storage without a database.
- YAML export and revalidation flow.
- Next.js workbench and Monaco editor integration.
- Demo sample text, generated sample outputs, reports, and submission docs.

## Third-party Dependencies

- Backend: FastAPI, LangGraph, Pydantic v2, jsonschema, ruamel.yaml, OpenAI-compatible client, pytest.
- Frontend: Next.js, React, TypeScript, Monaco Editor, monaco-yaml, Playwright.

## Known Limits

- MVP supports plain text and `.txt` only.
- It is optimized for short demo inputs, not full-length books.
- Mock mode is intentionally available so the demo does not depend on API keys or external model latency.
- Real LLM quality depends on the configured model.

## Final Checklist

- [ ] README top demo link is replaced.
- [ ] Narrated demo video is public or shareable.
- [ ] Repository is public from `2026-06-08 00:00` China time.
- [ ] `.\scripts\check.ps1` passes before final submission.
- [ ] The selected topic and repository URL are submitted at `hr.qiniu.com`.
