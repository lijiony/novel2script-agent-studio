# PR Plan And Suggested Descriptions

Use these descriptions when creating GitHub pull requests. Each PR should include feature description, implementation approach, and test method.

## PR: chore: harden demo and check scripts

Feature description:

Improves local demo reliability, submission verification, and final validation honesty. The Windows demo script now serves the frontend with a production build by default for clean screen recording, and a stop script is available to clean up local demo processes. The local check script now fails immediately when backend tests, frontend build, or Playwright smoke tests fail. Backend workflow runs now fail clearly if one automatic repair still leaves validation errors, and the YAML editor re-applies Monaco schema settings when the schema arrives after mount.

Implementation approach:

Adds `scripts/stop-demo.ps1`, updates `scripts/start-demo.ps1` with a `production` / `dev` frontend mode, copies Next.js standalone static assets for production serving, and adds native command exit-code checking to both demo and check scripts. The backend package configuration now only discovers the `app` package, so temporary `runs/` artifacts cannot break editable installs. The workflow marks unrepaired validation failures as `failed_validation`, and `RunStore.fail()` marks the current stage failed for clearer UI state. The YAML editor stores the Monaco instance and configures `monaco-yaml` whenever the schema becomes available. The root README documents the production demo flow, development mode, PR branch precheck, and stop command. Temporary frontend screenshots are ignored through `.gitignore`.

Test method:

- Ran `.\scripts\start-demo.ps1` and confirmed `http://127.0.0.1:8000/health` returns OK.
- Confirmed the production frontend responds at `http://127.0.0.1:3000`.
- Ran `.\scripts\stop-demo.ps1` and confirmed local demo processes are cleaned up.
- Ran targeted backend tests for run store and workflow failure handling.
- Ran `.\scripts\check.ps1`; 13 backend pytest tests, frontend build, and Playwright smoke test passed.

## PR: docs: add final demo rehearsal guide

Feature description:

Adds a final demo rehearsal guide and static generated sample outputs so reviewers can inspect the expected YAML/script artifacts without running the app first.

Implementation approach:

Adds `docs/final_demo_rehearsal.md` for recording preparation, adds generated sample files under `samples/`, and links those materials from the README. The files are generated from the project mock workflow using the included three-chapter novel sample.

Test method:

- Ran `.\scripts\check.ps1`.
- Confirmed backend tests, frontend build, and Playwright smoke test pass.
- Ran XEngineer submission readiness check and confirmed all commits are inside the third-batch time window.

## Earlier Development Evidence

The repository also contains visible commits for:

- Project scaffolding.
- Backend schema, run lifecycle, and mock workflow.
- Next.js YAML workbench.
- Frontend smoke workflow.
- CI and submission materials.
- Downloadable artifacts.
- Edited YAML download.
- API-key-free mock fallback.
- Structured intermediate workflow outputs.

## Merge Guidance

Merge the latest PR branch into `main` before final submission so the default branch contains the final demo scripts, rehearsal docs, and sample output files.
