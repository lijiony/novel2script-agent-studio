import json
from collections.abc import Iterator
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.core.config import Settings, get_settings
from app.dependencies import get_run_store
from app.domain.chapter_parser import ChapterParseError, parse_chapters
from app.domain.schemas import (
    Chapter,
    ChapterCard,
    ChapterChatMessage,
    ChapterChatMessagesResponse,
    ChapterChatRequest,
    ChapterReview,
    ChapterReviewItem,
    ChapterReviewsResponse,
    CreateRunResponse,
    GenerateRunRequest,
    RunListItem,
    RunListResponse,
    RunStatus,
    RunStatusResponse,
    YamlValidationRequest,
    YamlValidationResponse,
    now_iso,
)
from app.domain.validators import validate_yaml_text
from app.graph.workflow import AdaptationWorkflow
from app.services.tool_registry import ToolContext, ToolRegistry
from app.services.run_store import ALLOWED_ARTIFACTS, RunStore


router = APIRouter(prefix="/api", tags=["runs"])


@router.get("/runs", response_model=RunListResponse)
def list_runs(store: RunStore = Depends(get_run_store)) -> RunListResponse:
    items = []
    for manifest in store.list_manifests():
        try:
            input_text = store.read_input(manifest.run_id)
            title = next(
                (line.strip() for line in input_text.splitlines() if line.strip()),
                "未命名改编任务",
            )
        except Exception:
            title = "未命名改编任务"
        items.append(
            RunListItem(
                run_id=manifest.run_id,
                title=title[:40],
                status=manifest.status.value,
                current_stage=manifest.current_stage,
                artifacts=manifest.artifacts,
                created_at=manifest.created_at,
                updated_at=manifest.updated_at,
            )
        )
    return RunListResponse(runs=items)


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
    background_tasks.add_task(workflow.intake, manifest.run_id)
    return CreateRunResponse(run_id=manifest.run_id, status=manifest.status)


@router.get("/runs/{run_id}/chapter-reviews", response_model=ChapterReviewsResponse)
def get_chapter_reviews(
    run_id: str,
    store: RunStore = Depends(get_run_store),
) -> ChapterReviewsResponse:
    try:
        store.read_manifest(run_id)
        return _chapter_reviews_response(run_id, store)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Run chapter reviews not found.") from exc


@router.post("/runs/{run_id}/chapter-cards/{chapter_id}/approve", response_model=ChapterReviewsResponse)
def approve_chapter_card(
    run_id: str,
    chapter_id: str,
    settings: Settings = Depends(get_settings),
    store: RunStore = Depends(get_run_store),
) -> ChapterReviewsResponse:
    try:
        AdaptationWorkflow(settings, store).approve_chapter(run_id, chapter_id)
        return _chapter_reviews_response(run_id, store)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{run_id}/chapter-cards/approve-all", response_model=ChapterReviewsResponse)
def approve_all_chapter_cards(
    run_id: str,
    settings: Settings = Depends(get_settings),
    store: RunStore = Depends(get_run_store),
) -> ChapterReviewsResponse:
    try:
        AdaptationWorkflow(settings, store).approve_all_chapters(run_id)
        return _chapter_reviews_response(run_id, store)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{run_id}/chapter-cards/{chapter_id}/regenerate", response_model=ChapterReviewsResponse)
def regenerate_chapter_card(
    run_id: str,
    chapter_id: str,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    store: RunStore = Depends(get_run_store),
) -> ChapterReviewsResponse:
    try:
        store.read_manifest(run_id)
        background_tasks.add_task(
            AdaptationWorkflow(settings, store).regenerate_chapter,
            run_id,
            chapter_id,
        )
        return _chapter_reviews_response(run_id, store)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{run_id}/build-plan", response_model=CreateRunResponse)
def build_plan(
    run_id: str,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    store: RunStore = Depends(get_run_store),
) -> CreateRunResponse:
    try:
        manifest = store.read_manifest(run_id)
        _assert_reviews_approved(run_id, store)
        background_tasks.add_task(AdaptationWorkflow(settings, store).build_plan, manifest.run_id)
        return CreateRunResponse(run_id=manifest.run_id, status=manifest.status)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{run_id}/chapter-cards/{chapter_id}/chat/stream")
def chapter_chat_stream(
    run_id: str,
    chapter_id: str,
    request: ChapterChatRequest,
    store: RunStore = Depends(get_run_store),
) -> StreamingResponse:
    try:
        response = _chapter_reviews_response(run_id, store)
        item = next(
            (candidate for candidate in response.items if candidate.review.chapter_id == chapter_id),
            None,
        )
        if item is None or item.card is None:
            raise HTTPException(status_code=404, detail="Chapter card not found.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc

    user_message = ChapterChatMessage(
        id=str(uuid4()),
        chapter_id=chapter_id,
        role="user",
        content=request.message,
        created_at=now_iso(),
    )
    _append_chat_message(run_id, store, user_message)

    def event_stream() -> Iterator[str]:
        context = ToolContext(run_id=run_id, chapter_id=chapter_id)
        tools = ToolRegistry().available_tools(context)
        yield _sse("visible_thinking", {"content": "我正在重新核对这一章的人物、线索和改编机会。"})
        yield _sse(
            "tool_event",
            {
                "name": "tool_registry",
                "status": "disabled",
                "tools": [tool.__dict__ for tool in tools],
            },
        )
        answer = (
            f"我看了 {item.chapter.title} 的理解卡。当前摘要是：{item.card.summary} "
            "如果你觉得这一章读偏了，建议先点“重新理解”，我会只刷新这一章，"
            "不会影响其他已经通过的章节。你也可以在备注里指出必须保留的人物动机或线索。"
        )
        chunks = [answer[index : index + 28] for index in range(0, len(answer), 28)]
        collected = ""
        for chunk in chunks:
            collected += chunk
            yield _sse("assistant_delta", {"content": chunk})
        assistant_message = ChapterChatMessage(
            id=str(uuid4()),
            chapter_id=chapter_id,
            role="assistant",
            content=collected,
            created_at=now_iso(),
        )
        _append_chat_message(run_id, store, assistant_message)
        yield _sse("final", {"content": collected})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get(
    "/runs/{run_id}/chapter-cards/{chapter_id}/chat/messages",
    response_model=ChapterChatMessagesResponse,
)
def get_chapter_chat_messages(
    run_id: str,
    chapter_id: str,
    store: RunStore = Depends(get_run_store),
) -> ChapterChatMessagesResponse:
    try:
        store.read_manifest(run_id)
        raw_messages = store.read_json(run_id, "chapter_chat_messages.json")
    except FileNotFoundError:
        raw_messages = []
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc
    messages = [
        ChapterChatMessage.model_validate(item)
        for item in raw_messages
        if item.get("chapter_id") == chapter_id
    ]
    return ChapterChatMessagesResponse(messages=messages)


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
        manifest = store.read_manifest(run_id)
        if artifact not in manifest.artifacts:
            raise HTTPException(status_code=404, detail="Artifact not found.")
        path = store.artifact_path(run_id, artifact)
    except HTTPException:
        raise
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


def _chapter_reviews_response(run_id: str, store: RunStore) -> ChapterReviewsResponse:
    chapters = [Chapter.model_validate(item) for item in store.read_json(run_id, "chapters.json")]
    try:
        cards = [
            ChapterCard.model_validate(item)
            for item in store.read_json(run_id, "chapter_cards.json")
        ]
    except Exception:
        cards = []
    reviews = [
        ChapterReview.model_validate(item)
        for item in store.read_json(run_id, "chapter_reviews.json")
    ]
    cards_by_id = {card.chapter_id: card for card in cards}
    reviews_by_id = {review.chapter_id: review for review in reviews}
    items = []
    for chapter in chapters:
        chapter_id = f"ch_{chapter.index:03d}"
        items.append(
            ChapterReviewItem(
                chapter=chapter,
                card=cards_by_id.get(chapter_id),
                review=reviews_by_id.get(chapter_id) or ChapterReview(chapter_id=chapter_id),
            )
        )
    return ChapterReviewsResponse(run_id=run_id, items=items)


def _assert_reviews_approved(run_id: str, store: RunStore) -> None:
    reviews = _chapter_reviews_response(run_id, store)
    blocked = [
        item.review.chapter_id
        for item in reviews.items
        if item.review.status != "approved" or item.card is None
    ]
    if blocked:
        raise HTTPException(
            status_code=409,
            detail="All chapter cards must be approved before building the adaptation plan.",
        )


def _append_chat_message(
    run_id: str,
    store: RunStore,
    message: ChapterChatMessage,
) -> None:
    try:
        messages = list(store.read_json(run_id, "chapter_chat_messages.json"))
    except Exception:
        messages = []
    messages.append(message.model_dump(mode="json"))
    store.write_json(run_id, "chapter_chat_messages.json", messages)


def _sse(event_type: str, payload: dict[str, object]) -> str:
    return "data: " + json.dumps({"type": event_type, **payload}, ensure_ascii=False) + "\n\n"
