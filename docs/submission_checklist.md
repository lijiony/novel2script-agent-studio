# XEngineer Submission Checklist

## Hard Rules

- [ ] Repository was created after `2026-06-05 00:00` China time.
- [ ] All commits are within `2026-06-05 00:00` to `2026-06-07 23:59` China time.
- [ ] Topic and repository URL were submitted at `hr.qiniu.com` within 24 hours.
- [ ] Repository is public from `2026-06-08 00:00` China time.
- [ ] Demo video is public or accessible from `2026-06-08 00:00` China time.
- [ ] Demo link placeholders were replaced with `.\scripts\set-demo-link.ps1 -DemoUrl "<url>"`.

## Repository Evidence

- [ ] Small, continuous commits are visible.
- [ ] Feature branches or PRs show development process.
- [ ] PR descriptions include feature description, implementation approach, and test method.
- [ ] README top section contains the demo video link.
- [ ] README explains setup, dependencies, original work, and known limits.

## Product Requirements

- [ ] User can paste or upload `.txt` novel input.
- [ ] Fewer than 3 chapters are rejected.
- [ ] 3+ chapters produce structured `script.json`.
- [ ] Program exports `script.yaml`.
- [ ] `schema.json` and `schema.md` are available.
- [ ] User can edit YAML and revalidate it.
- [ ] `adaptation_report.md` is generated and downloadable.
- [ ] Mock mode works without an API key.

## Verification

- [ ] Local demo starts with `.\scripts\start-demo.ps1`.
- [ ] Full local checks pass with `.\scripts\check.ps1`.
- [ ] Strict submission readiness passes with `.\scripts\check-submission-ready.ps1`.
- [ ] Backend tests pass.
- [ ] Frontend build passes.
- [ ] Playwright smoke test passes.
- [ ] Demo path is rehearsed once before recording.
