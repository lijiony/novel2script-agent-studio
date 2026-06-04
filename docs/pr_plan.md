# PR Plan And Suggested Descriptions

Use these descriptions when creating GitHub pull requests. Each PR should include feature description, implementation approach, and test method.

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

Merge this PR into `main` before final submission so the default branch contains the latest demo rehearsal and sample output files.
