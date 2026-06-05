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
2. Open the app and show the three-column co-writer workbench.
3. Show the three-chapter sample novel already loaded, then click `分析小说`.
4. Pause on the middle planning panel and show the AI adaptation plan:
   recommended format, style, scale, scene plan, and risks.
5. Choose `短剧`, `忠实版`, and `心理外化`; point out preserve/forbidden-change notes.
6. Click `生成剧本`.
7. Pause on the workflow panel and name the fixed LangGraph stages:
   `validate_input`, `parse_chapters`, `extract_story_facts`, `plan_adaptation`, `await_author_controls`, `generate_script_json`, `validate_schema`, `export_yaml`, `generate_report`.
8. Show the generated YAML editor.
9. Point out `adaptation_profile`, `adaptation_strategy`, `source_excerpt`, `conflict`, `emotional_shift`, `ai_added_content`, `revision_suggestions`, and `origin`.
10. Edit one dialogue line.
11. Click `重新校验 YAML` and show the validation success message.
12. Click or point to downloads for `adaptation_plan.md`, `script.yaml`, `schema.json`, `schema.md`, and `adaptation_report.md`.
13. Open `docs/schema.md` or mention it is generated from the Pydantic source-of-truth model.

## Optional Failure Demo

If time allows, briefly remove one chapter from the input and show that the backend rejects fewer than three chapters. Keep this short so the main successful path remains clear.

## Narration Points

- The project does not use a database; every run uses a temporary UUID directory.
- The app first plans the adaptation, then generates after author controls are selected.
- The LLM never writes YAML directly. It produces structured JSON, then the app validates it and exports YAML.
- Pydantic v2 is the schema source of truth.
- Reader and planner intermediate outputs are also structured and validated.
- YAML stores why the AI adapted each scene, including conflict, emotional shift, source excerpt, AI additions, suggestions, and production risks.
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
