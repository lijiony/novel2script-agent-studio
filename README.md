# Novel2Script Agent Studio

> Demo video: TODO - add the narrated public demo link here before final submission.

XEngineer third-batch topic: **AI novel-to-script tool**.

Novel2Script Agent Studio is a lightweight, stateless AI workbench that converts 3+ chapters of novel text into an editable screenplay YAML draft. The backend runs a fixed LangGraph pipeline, validates structured JSON with Pydantic and JSON Schema, exports YAML with `ruamel.yaml`, and returns a validation report for editing and download.

## Core Features

- Paste novel text or upload a `.txt` file.
- Reject inputs with fewer than 3 detected chapters.
- Run a fixed AI adaptation workflow: input validation, chapter parsing, story fact extraction, scene planning, script JSON generation, schema review, one repair attempt, YAML export, and report generation.
- Generate `script.json`, `script.yaml`, `schema.json`, `schema.md`, and `adaptation_report.md`.
- Edit YAML in the browser and revalidate it through the backend.
- Run without an API key in `USE_MOCK_LLM=true` mode for stable demos.

## Architecture

```text
frontend/
  Next.js + React + TypeScript
  Monaco Editor + YAML validation fallback

backend/
  FastAPI
  LangGraph fixed workflow
  Pydantic v2 schema source of truth
  jsonschema semantic validation
  ruamel.yaml export

runs/{run_id}/
  Temporary run artifacts, no database
```

The system intentionally uses a fixed workflow instead of a free-form autonomous agent. This keeps the demo traceable, reproducible, and easier to evaluate.

## Quick Start

Clone the repository, then run backend and frontend in two terminals.

For a stable local demo on Windows, run:

```powershell
.\scripts\start-demo.ps1
```

Then open `http://127.0.0.1:3000`.

### Backend

```powershell
cd backend
uv venv
.venv\Scripts\Activate.ps1
uv pip install -e ".[dev]"
$env:USE_MOCK_LLM="true"
uvicorn app.main:app --reload --port 8000
```

Health check:

```text
http://127.0.0.1:8000/health
```

### Frontend

```powershell
cd frontend
npm install
npm run dev:local
```

Open `http://localhost:3000`.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/runs` | Create a run from pasted text or `.txt` upload |
| `GET` | `/api/runs/{run_id}` | Poll run status, current stage, and artifacts |
| `GET` | `/api/runs/{run_id}/artifacts/{name}` | Download a whitelisted artifact |
| `POST` | `/api/runs/{run_id}/validate-yaml` | Validate edited YAML |
| `GET` | `/api/schema/script` | Return the generated JSON Schema |

## Tests

Run all local checks on Windows:

```powershell
.\scripts\check.ps1
```

Backend:

```powershell
cd backend
.venv\Scripts\python -m pytest
```

Frontend build:

```powershell
cd frontend
npm run build
```

Frontend smoke test:

```powershell
cd frontend
npx playwright install chromium
npx playwright test
```

## Environment

Backend environment variables:

- `USE_MOCK_LLM`: defaults to `true`; keeps the full workflow demoable without an API key.
- `OPENAI_API_KEY`: optional, used only when `USE_MOCK_LLM=false`; if no key is provided, the backend keeps using mock mode for demo safety.
- `OPENAI_BASE_URL`: optional OpenAI-compatible API base URL.
- `OPENAI_MODEL`: optional, defaults to `gpt-4o-mini`.
- `RUNS_DIR`: optional, defaults to `runs`.

Frontend environment variables:

- `NEXT_PUBLIC_API_BASE_URL`: defaults to `http://127.0.0.1:8000`.

## YAML Schema

The schema is defined in Pydantic v2 models under `backend/app/domain/schemas.py`. The backend exposes the generated JSON Schema at:

```text
GET /api/schema/script
```

The human-readable schema document lives at `docs/schema.md` and is also written into each run directory as `schema.md`.

## LangGraph Workflow

```text
validate_input
 -> parse_chapters
 -> extract_story_facts
 -> plan_scenes
 -> generate_script_json
 -> validate_schema
 -> repair_once_if_needed
 -> export_yaml
 -> generate_report
```

The workflow is fixed by design. Each stage writes traceable artifacts into `runs/{run_id}` so the final YAML can be explained and debugged.

## Original Work

Original parts of this project:

- Novel-to-script workflow design.
- Pydantic screenplay schema.
- LangGraph fixed adaptation pipeline.
- Run artifact storage design without a database.
- YAML export and validation flow.
- Frontend editing and download workflow.
- Sample text, validation report format, and README/demo materials.

Third-party libraries are listed in `backend/pyproject.toml` and `frontend/package.json`.

## Known Limits

- MVP supports plain text and `.txt` input only.
- Long-form novels are intentionally limited for demo stability.
- Mock mode generates deterministic sample-like output for reliable presentation.
- Real LLM quality depends on the configured model and API availability.

## Submission Notes

- Repository must be created after `2026-06-05 00:00` China time.
- All commits must be inside the third-batch work window.
- Keep small PRs with clear title, feature description, implementation approach, and test method.
- Add the narrated demo link at the top of this README before final submission.

See also:

- `docs/schema.md`
- `docs/demo_script.md`
- `docs/submission_checklist.md`
