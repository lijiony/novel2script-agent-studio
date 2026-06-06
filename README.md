# Novel2Script Agent Studio

> Demo video: TODO - add the narrated public demo link here before final submission.

XEngineer third-batch topic: **AI novel-to-script tool**.

Novel2Script Agent Studio is a lightweight, stateless AI co-writer workbench that helps authors adapt 3+ chapters of novel text into a performable, editable, and traceable screenplay YAML draft. It first analyzes the novel and proposes an adaptation plan, then lets the author choose script format, style focus, adaptation scale, preserved content, forbidden changes, and notes before generation.

The backend runs fixed LangGraph workflows, validates structured JSON with Pydantic and JSON Schema, exports YAML with `ruamel.yaml`, and returns planning and validation reports for editing and download.

## Core Features

- Paste novel text or upload a `.txt` file.
- Reject inputs with fewer than 3 detected chapters.
- Analyze the source first: chapter parsing, story fact extraction, scene planning, adaptation risks, and format recommendations.
- Let authors choose format, style, scale, preserved items, forbidden changes, and free-form notes before generation.
- Generate traceable artifacts: `adaptation_plan.json`, `adaptation_plan.md`, `script.json`, `script.yaml`, `schema.json`, `schema.md`, and `adaptation_report.md`.
- Store scene purpose, conflict, emotional shift, source excerpt, AI-added content, revision suggestions, production risk, and content origin markers in YAML.
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

The system intentionally uses fixed, role-like LangGraph workflows instead of a free-form autonomous agent. This keeps the demo traceable, reproducible, and easier to evaluate while still behaving like an AI adaptation co-writer.

## Quick Start

Clone the repository, then run backend and frontend in two terminals.

For a stable local demo on Windows, run:

```powershell
.\scripts\start-demo.ps1
```

This starts the backend in mock mode and serves the frontend with a production build for clean screen recording. Then open `http://127.0.0.1:3000`.

For iterative frontend development, run:

```powershell
.\scripts\start-demo.ps1 -FrontendMode dev
```

To stop local demo processes:

```powershell
.\scripts\stop-demo.ps1
```

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
| `GET` | `/api/runs` | List local run tasks for the Codex-style sidebar |
| `POST` | `/api/runs/intake` | Create a run, validate chapters, and generate chapter understanding cards |
| `GET` | `/api/runs/{run_id}/chapter-reviews` | Read chapter cards and author review state |
| `POST` | `/api/runs/{run_id}/chapter-cards/approve-all` | Approve all chapter understanding cards |
| `POST` | `/api/runs/{run_id}/build-plan` | Build Story Bible and adaptation plan after chapter approval |
| `POST` | `/api/runs/{run_id}/chapter-script-cards/generate` | Generate per-chapter script cards from the plan and author controls |
| `GET` | `/api/runs/{run_id}/chapter-script-reviews` | Read script cards and author review state |
| `POST` | `/api/runs/{run_id}/continuity-merge` | Merge approved script cards into final JSON/YAML |
| `POST` | `/api/runs/{run_id}/final-feedback` | Record final dissatisfaction and suggest a repair path |
| `POST` | `/api/runs/{run_id}/final-confirm` | Confirm the final script |
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

Submission readiness precheck:

```powershell
.\scripts\check-submission-ready.ps1 -AllowMissingDemo
```

When checking an open PR branch before merge:

```powershell
.\scripts\check-submission-ready.ps1 -AllowMissingDemo -AllowNonMain
```

After uploading the narrated video, update the placeholders with:

```powershell
.\scripts\set-demo-link.ps1 -DemoUrl "<your video URL>"
```

Before final submission, run the strict version:

```powershell
.\scripts\check-submission-ready.ps1
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

## Sample Output

Static sample artifacts are included for quick review:

- `samples/three_chapter_novel.txt`
- `samples/sample_adaptation_plan.md`
- `samples/sample_script.json`
- `samples/sample_script.yaml`
- `samples/sample_adaptation_report.md`

They are generated by the mock workflow and show the expected planning and screenplay YAML shape before reviewers run the app locally.

## LangGraph Workflow

```text
validate_input
 -> parse_chapters
 -> read_chapters_individually
 -> await_chapter_review
 -> build_story_bible
 -> plan_adaptation
 -> await_author_controls
 -> generate_chapter_script_cards
 -> await_script_review
 -> continuity_merge
 -> generate_script_json
 -> validate_schema
 -> repair_once_if_needed
 -> export_yaml
 -> generate_report
```

The workflow is fixed by design, but split into author-visible checkpoints:

1. Chapter review: detect chapters, generate chapter understanding cards, and let the author approve or regenerate them.
2. Planning: build `story_bible.json/md` and `adaptation_plan.json/md` from approved chapter cards.
3. Script card review: apply author controls and generate one script card per selected chapter.
4. Continuity merge: merge approved script cards into validated `script.json`, export `script.yaml`, and generate reports.
5. Final review: let the author confirm the result or send feedback back to continuity merge / one chapter script card.

Each stage writes traceable artifacts into `runs/{run_id}` so the final YAML can be explained and debugged.
Reader and planner intermediate outputs are also validated with Pydantic models before they are written to disk.

## Original Work

Original parts of this project:

- Novel-to-script workflow design.
- Pydantic screenplay schema.
- Two-stage LangGraph adaptation co-writer workflow.
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
- `docs/final_demo_rehearsal.md`
- `docs/submission_summary.md`
- `docs/pr_plan.md`
- `docs/submission_checklist.md`
