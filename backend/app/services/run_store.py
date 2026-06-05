import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from app.domain.schemas import RunManifest, RunStage, RunStatus, now_iso


ALLOWED_ARTIFACTS = {
    "manifest.json",
    "input.txt",
    "chapters.json",
    "reader_output.json",
    "planner_output.json",
    "adaptation_plan.json",
    "adaptation_plan.md",
    "author_controls.json",
    "script.json",
    "script.yaml",
    "schema.json",
    "schema.md",
    "adaptation_report.md",
    "report.json",
}

WORKFLOW_STAGES = [
    "validate_input",
    "parse_chapters",
    "extract_story_facts",
    "plan_adaptation",
    "await_author_controls",
    "generate_script_json",
    "validate_schema",
    "repair_once_if_needed",
    "export_yaml",
    "generate_report",
]


class RunStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create_run(self, input_text: str) -> RunManifest:
        run_id = str(uuid4())
        run_dir = self.run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=False)
        stages = [RunStage(name=name) for name in WORKFLOW_STAGES]
        manifest = RunManifest(
            run_id=run_id,
            status=RunStatus.queued,
            current_stage=None,
            stages=stages,
            artifacts=["manifest.json", "input.txt"],
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        self.write_text(run_id, "input.txt", input_text)
        self.write_manifest(manifest)
        return manifest

    def run_dir(self, run_id: str) -> Path:
        safe_id = self._validate_run_id(run_id)
        return self.root / safe_id

    def read_manifest(self, run_id: str) -> RunManifest:
        path = self.run_dir(run_id) / "manifest.json"
        return RunManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def write_manifest(self, manifest: RunManifest) -> None:
        manifest.updated_at = now_iso()
        self._atomic_write(
            self.run_dir(manifest.run_id) / "manifest.json",
            manifest.model_dump_json(indent=2),
        )

    def read_input(self, run_id: str) -> str:
        return self.read_text(run_id, "input.txt")

    def read_text(self, run_id: str, artifact: str) -> str:
        path = self.artifact_path(run_id, artifact)
        return path.read_text(encoding="utf-8")

    def write_text(self, run_id: str, artifact: str, content: str) -> None:
        path = self.artifact_path(run_id, artifact)
        self._atomic_write(path, content)
        self._add_artifact(run_id, artifact)

    def write_json(self, run_id: str, artifact: str, payload: object) -> None:
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        self.write_text(run_id, artifact, content)

    def read_json(self, run_id: str, artifact: str) -> object:
        return json.loads(self.read_text(run_id, artifact))

    def artifact_path(self, run_id: str, artifact: str) -> Path:
        if artifact not in ALLOWED_ARTIFACTS:
            raise ValueError(f"Artifact '{artifact}' is not allowed.")
        path = self.run_dir(run_id) / artifact
        resolved = path.resolve()
        run_root = self.run_dir(run_id).resolve()
        if run_root not in resolved.parents and resolved != run_root:
            raise ValueError("Artifact path escapes run directory.")
        return resolved

    def set_stage(
        self,
        run_id: str,
        stage_name: str,
        status: str,
        *,
        message: str | None = None,
        run_status: RunStatus | None = None,
    ) -> RunManifest:
        manifest = self.read_manifest(run_id)
        manifest.current_stage = stage_name
        if run_status:
            manifest.status = run_status
        for stage in manifest.stages:
            if stage.name == stage_name:
                stage.status = status  # type: ignore[assignment]
                stage.message = message
                if status == "running":
                    stage.started_at = now_iso()
                if status in {"succeeded", "failed"}:
                    stage.finished_at = now_iso()
                break
        self.write_manifest(manifest)
        return manifest

    def fail(self, run_id: str, status: RunStatus, error: str) -> RunManifest:
        manifest = self.read_manifest(run_id)
        manifest.status = status
        manifest.error = error
        if manifest.current_stage:
            for stage in manifest.stages:
                if stage.name == manifest.current_stage and stage.status == "running":
                    stage.status = "failed"
                    stage.message = error
                    stage.finished_at = now_iso()
                    break
        self.write_manifest(manifest)
        return manifest

    def succeed(self, run_id: str) -> RunManifest:
        manifest = self.read_manifest(run_id)
        manifest.status = RunStatus.succeeded
        manifest.current_stage = None
        manifest.error = None
        self.write_manifest(manifest)
        return manifest

    def planned(self, run_id: str) -> RunManifest:
        manifest = self.read_manifest(run_id)
        manifest.status = RunStatus.planned
        manifest.current_stage = None
        manifest.error = None
        self.write_manifest(manifest)
        return manifest

    def cleanup_expired(self, ttl_hours: int) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
        for child in self.root.iterdir():
            if not child.is_dir():
                continue
            manifest_path = child / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                manifest = RunManifest.model_validate_json(
                    manifest_path.read_text(encoding="utf-8")
                )
                updated = datetime.fromisoformat(manifest.updated_at)
            except Exception:
                continue
            if updated < cutoff:
                shutil.rmtree(child, ignore_errors=True)

    def _add_artifact(self, run_id: str, artifact: str) -> None:
        if artifact == "manifest.json":
            return
        manifest_path = self.run_dir(run_id) / "manifest.json"
        if not manifest_path.exists():
            return
        manifest = self.read_manifest(run_id)
        if artifact not in manifest.artifacts:
            manifest.artifacts.append(artifact)
            self.write_manifest(manifest)

    @staticmethod
    def _validate_run_id(run_id: str) -> str:
        parsed = UUID(run_id)
        return str(parsed)

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)
