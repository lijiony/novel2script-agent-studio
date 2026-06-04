# Final Demo Rehearsal

Use this checklist immediately before recording the narrated demo video.

## Start The Demo Environment

```powershell
.\scripts\start-demo.ps1
```

Open:

```text
http://127.0.0.1:3000
```

The demo script starts the backend in mock mode so the recording does not depend on an API key or external model latency.

## Rehearsal Path

1. Show the README top section and mention this is the XEngineer third-batch topic: AI novel-to-script tool.
2. Open the app and show the three-chapter sample novel already loaded.
3. Click `开始改编`.
4. Pause on the workflow panel and name the fixed LangGraph stages:
   `validate_input`, `parse_chapters`, `extract_story_facts`, `plan_scenes`, `generate_script_json`, `validate_schema`, `export_yaml`, `generate_report`.
5. Show the generated YAML editor.
6. Point out `metadata`, `characters`, `scenes.source_chapters`, `actions`, `dialogues`, and `adaptation_notes`.
7. Edit one dialogue line.
8. Click `重新校验 YAML` and show the validation success message.
9. Click or point to downloads for `script.yaml`, `schema.json`, `schema.md`, and `adaptation_report.md`.
10. Open `docs/schema.md` or mention it is generated from the Pydantic source-of-truth model.

## Optional Failure Demo

If time allows, briefly remove one chapter from the input and show that the backend rejects fewer than three chapters. Keep this short so the main successful path remains clear.

## Narration Points

- The project does not use a database; every run uses a temporary UUID directory.
- The LLM never writes YAML directly. It produces structured JSON, then the app validates it and exports YAML.
- Pydantic v2 is the schema source of truth.
- Reader and planner intermediate outputs are also structured and validated.
- Mock mode keeps the demo reproducible without an API key.

## After Recording

- Upload the narrated video to a public-accessible platform.
- Replace demo-link placeholders with:

```powershell
.\scripts\set-demo-link.ps1 -DemoUrl "https://example.com/your-demo-video"
```

- Run:

```powershell
.\scripts\check.ps1
```

- Confirm the repository and video will be public from `2026-06-08 00:00` China time.
