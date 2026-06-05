from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.config import Settings, get_settings
from app.dependencies import get_run_store
from app.domain.chapter_parser import ChapterParseError, parse_chapters
from app.domain.schemas import (
    CreateRunResponse,
    GenerateRunRequest,
    RunStatus,
    RunStatusResponse,
    YamlValidationRequest,
    YamlValidationResponse,
)
from app.domain.validators import validate_yaml_text
from app.graph.workflow import AdaptationWorkflow
from app.services.run_store import ALLOWED_ARTIFACTS, RunStore


router = APIRouter(prefix="/api", tags=["runs"])


@router.post("/runs", response_model=CreateRunResponse)
async def create_run(
    background_tasks: BackgroundTasks,
    text: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    settings: Settings = Depends(get_settings),
    store: RunStore = Depends(get_run_store),
) -> CreateRunResponse:
    input_text = await _read_input(text, file)
    if len(input_text) > settings.max_input_chars:
        raise HTTPException(
            status_code=413,
            detail=f"Input is too long. Limit is {settings.max_input_chars} characters.",
        )
    _assert_three_chapters(input_text, settings)
    manifest = store.create_run(input_text)
    workflow = AdaptationWorkflow(settings, store)
    background_tasks.add_task(workflow.run, manifest.run_id)
    return CreateRunResponse(run_id=manifest.run_id, status=manifest.status)


@router.post("/runs/intake", response_model=CreateRunResponse)
async def intake_run(
    background_tasks: BackgroundTasks,
    text: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    settings: Settings = Depends(get_settings),
    store: RunStore = Depends(get_run_store),
) -> CreateRunResponse:
    input_text = await _read_input(text, file)
    if len(input_text) > settings.max_input_chars:
        raise HTTPException(
            status_code=413,
            detail=f"Input is too long. Limit is {settings.max_input_chars} characters.",
        )
    _assert_three_chapters(input_text, settings)
    manifest = store.create_run(input_text)
    workflow = AdaptationWorkflow(settings, store)
    background_tasks.add_task(workflow.plan, manifest.run_id)
    return CreateRunResponse(run_id=manifest.run_id, status=manifest.status)


@router.post("/runs/{run_id}/generate", response_model=CreateRunResponse)
def generate_run(
    run_id: str,
    request: GenerateRunRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    store: RunStore = Depends(get_run_store),
) -> CreateRunResponse:
    try:
        manifest = store.read_manifest(run_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc
    if "adaptation_plan.json" not in manifest.artifacts:
        raise HTTPException(status_code=400, detail="Run must complete intake planning first.")
    if manifest.status not in {RunStatus.planned, RunStatus.succeeded, RunStatus.failed_validation}:
        raise HTTPException(status_code=409, detail="Run is not ready for generation.")
    workflow = AdaptationWorkflow(settings, store)
    background_tasks.add_task(workflow.generate, manifest.run_id, request.controls)
    return CreateRunResponse(run_id=manifest.run_id, status=manifest.status)


@router.get("/runs/{run_id}", response_model=RunStatusResponse)
def get_run(run_id: str, store: RunStore = Depends(get_run_store)) -> RunStatusResponse:
    try:
        manifest = store.read_manifest(run_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc
    return RunStatusResponse(
        run_id=manifest.run_id,
        status=manifest.status,
        current_stage=manifest.current_stage,
        stages=manifest.stages,
        artifacts=manifest.artifacts,
        error=manifest.error,
    )


@router.get("/runs/{run_id}/artifacts/{artifact}")
def get_artifact(run_id: str, artifact: str, store: RunStore = Depends(get_run_store)):
    if artifact not in ALLOWED_ARTIFACTS:
        raise HTTPException(status_code=404, detail="Artifact is not allowed.")
    try:
        path = store.artifact_path(run_id, artifact)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return FileResponse(
        path,
        filename=artifact,
        media_type=_artifact_media_type(artifact),
    )


@router.post("/runs/{run_id}/validate-yaml", response_model=YamlValidationResponse)
def validate_yaml(
    run_id: str,
    request: YamlValidationRequest,
    store: RunStore = Depends(get_run_store),
) -> YamlValidationResponse:
    try:
        store.read_manifest(run_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc
    return YamlValidationResponse(report=validate_yaml_text(request.yaml_text))


async def _read_input(text: str | None, file: UploadFile | None) -> str:
    if file is not None:
        if not file.filename or not file.filename.lower().endswith(".txt"):
            raise HTTPException(status_code=400, detail="Only .txt files are supported.")
        raw = await file.read()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="File must be UTF-8 text.") from exc
    if text is not None and text.strip():
        return text
    raise HTTPException(status_code=400, detail="Provide novel text or a .txt file.")


def _assert_three_chapters(input_text: str, settings: Settings) -> None:
    try:
        parse_chapters(input_text, max_chars=settings.max_input_chars)
    except ChapterParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _artifact_media_type(artifact: str) -> str:
    if artifact.endswith(".json"):
        return "application/json"
    if artifact.endswith(".yaml"):
        return "application/x-yaml"
    if artifact.endswith(".md"):
        return "text/markdown"
    if artifact.endswith(".txt"):
        return "text/plain"
    return "application/octet-stream"
