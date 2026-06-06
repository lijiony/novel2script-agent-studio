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
    ChapterScriptCard,
    ChapterScriptReview,
    ChapterScriptReviewItem,
    ChapterScriptReviewsResponse,
    CreateRunResponse,
    ApplyFinalFeedbackRequest,
    FinalFeedbackRequest,
    FinalFeedbackResponse,
    GenerateRunRequest,
    RunListItem,
    RunListResponse,
    RunStatus,
    RunStatusResponse,
    ScriptFeedback,
    YamlValidationRequest,
    YamlValidationResponse,
    now_iso,
)
from app.domain.validators import validate_yaml_text
from app.graph.workflow import AdaptationWorkflow
from app.services.llm_client import LlmClient
from app.services.run_store import ALLOWED_ARTIFACTS, RunStore


router = APIRouter(prefix="/api", tags=["runs"])


def _assert_manifest_status(
    status: RunStatus,
    expected: set[RunStatus],
    detail: str,
) -> None:
    if status not in expected:
        raise HTTPException(status_code=409, detail=detail)


def _mark_chapter_review_regenerating(
    run_id: str,
    store: RunStore,
    chapter_id: str,
) -> None:
    reviews = [
        ChapterReview.model_validate(item)
        for item in store.read_json(run_id, "chapter_reviews.json")
    ]
    if chapter_id not in {review.chapter_id for review in reviews}:
        raise HTTPException(status_code=404, detail="Chapter review not found.")
    next_reviews = [
        review.model_copy(
            update={"status": "regenerating", "approved_at": None, "error": None}
        )
        if review.chapter_id == chapter_id
        else review
        for review in reviews
    ]
    store.write_json(
        run_id,
        "chapter_reviews.json",
        [review.model_dump(mode="json") for review in next_reviews],
    )


def _mark_chapter_script_review_regenerating(
    run_id: str,
    store: RunStore,
    chapter_id: str,
) -> None:
    reviews = [
        ChapterScriptReview.model_validate(item)
        for item in store.read_json(run_id, "chapter_script_reviews.json")
    ]
    if chapter_id not in {review.chapter_id for review in reviews}:
        raise HTTPException(status_code=404, detail="Chapter script review not found.")
    next_reviews = [
        review.model_copy(
            update={"status": "regenerating", "approved_at": None, "error": None}
        )
        if review.chapter_id == chapter_id
        else review
        for review in reviews
    ]
    store.write_json(
        run_id,
        "chapter_script_reviews.json",
        [review.model_dump(mode="json") for review in next_reviews],
    )


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
        manifest = store.read_manifest(run_id)
        _assert_manifest_status(
            manifest.status,
            {RunStatus.awaiting_chapter_review},
            "Run is not awaiting chapter review.",
        )
        AdaptationWorkflow(settings, store).approve_chapter(run_id, chapter_id)
        return _chapter_reviews_response(run_id, store)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{run_id}/chapter-cards/approve-all", response_model=ChapterReviewsResponse)
def approve_all_chapter_cards(
    run_id: str,
    settings: Settings = Depends(get_settings),
    store: RunStore = Depends(get_run_store),
) -> ChapterReviewsResponse:
    try:
        manifest = store.read_manifest(run_id)
        _assert_manifest_status(
            manifest.status,
            {RunStatus.awaiting_chapter_review},
            "Run is not awaiting chapter review.",
        )
        AdaptationWorkflow(settings, store).approve_all_chapters(run_id)
        return _chapter_reviews_response(run_id, store)
    except HTTPException:
        raise
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
        manifest = store.read_manifest(run_id)
        _assert_manifest_status(
            manifest.status,
            {RunStatus.awaiting_chapter_review},
            "Run is not awaiting chapter review.",
        )
        feedback_notes = _discussion_notes(run_id, store, chapter_id, "chapter_chat_messages.json")
        _mark_chapter_review_regenerating(run_id, store, chapter_id)
        store.set_stage(
            run_id,
            "regenerate_chapter",
            "running",
            message=f"Regenerating {chapter_id}.",
            run_status=RunStatus.regenerating_chapter,
        )
        background_tasks.add_task(
            AdaptationWorkflow(settings, store).regenerate_chapter,
            run_id,
            chapter_id,
            feedback_notes,
        )
        return _chapter_reviews_response(run_id, store)
    except HTTPException:
        raise
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
        if manifest.status in {RunStatus.planning, RunStatus.planned}:
            return CreateRunResponse(run_id=manifest.run_id, status=manifest.status)
        _assert_manifest_status(
            manifest.status,
            {RunStatus.awaiting_chapter_review},
            "Run is not awaiting chapter review.",
        )
        _assert_reviews_approved(run_id, store)
        manifest = store.set_stage(
            run_id,
            "build_story_bible",
            "running",
            message="Building Story Bible from approved chapter cards.",
            run_status=RunStatus.planning,
        )
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
    settings: Settings = Depends(get_settings),
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
    chat_messages = _chat_messages_for_chapter(run_id, store, chapter_id)

    def event_stream() -> Iterator[str]:
        yield _sse("visible_thinking", {"content": "我正在对照原文、理解卡和你刚才的反馈，判断哪里可能读偏。"})
        answer = _chapter_discussion_answer(settings, item.chapter, item.card, chat_messages)
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


@router.post("/runs/{run_id}/chapter-script-cards/generate", response_model=CreateRunResponse)
def generate_chapter_script_cards(
    run_id: str,
    background_tasks: BackgroundTasks,
    request: GenerateRunRequest | None = None,
    settings: Settings = Depends(get_settings),
    store: RunStore = Depends(get_run_store),
) -> CreateRunResponse:
    try:
        manifest = store.read_manifest(run_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc
    if manifest.status in {RunStatus.generating_chapter_scripts, RunStatus.awaiting_script_review}:
        return CreateRunResponse(run_id=manifest.run_id, status=manifest.status)
    if manifest.status != RunStatus.planned:
        raise HTTPException(status_code=409, detail="Run must be planned before chapter script generation.")
    if request and request.controls.generation_scope:
        _assert_generation_scope_approved(run_id, store, request.controls.generation_scope)
    workflow = AdaptationWorkflow(settings, store)
    manifest = store.set_stage(
        run_id,
        "generate_chapter_script_cards",
        "running",
        message="Generating chapter script cards from the selected chapter scope.",
        run_status=RunStatus.generating_chapter_scripts,
    )
    background_tasks.add_task(
        workflow.generate,
        manifest.run_id,
        (request.controls if request else None),
    )
    return CreateRunResponse(run_id=manifest.run_id, status=manifest.status)


@router.get("/runs/{run_id}/chapter-script-reviews", response_model=ChapterScriptReviewsResponse)
def get_chapter_script_reviews(
    run_id: str,
    store: RunStore = Depends(get_run_store),
) -> ChapterScriptReviewsResponse:
    try:
        store.read_manifest(run_id)
        return _chapter_script_reviews_response(run_id, store)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Run chapter script reviews not found.") from exc


@router.post(
    "/runs/{run_id}/chapter-script-cards/{chapter_id}/approve",
    response_model=ChapterScriptReviewsResponse,
)
def approve_chapter_script_card(
    run_id: str,
    chapter_id: str,
    settings: Settings = Depends(get_settings),
    store: RunStore = Depends(get_run_store),
) -> ChapterScriptReviewsResponse:
    try:
        manifest = store.read_manifest(run_id)
        _assert_manifest_status(
            manifest.status,
            {RunStatus.awaiting_script_review},
            "Run is not awaiting chapter script review.",
        )
        AdaptationWorkflow(settings, store).approve_chapter_script(run_id, chapter_id)
        return _chapter_script_reviews_response(run_id, store)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/runs/{run_id}/chapter-script-cards/approve-all",
    response_model=ChapterScriptReviewsResponse,
)
def approve_all_chapter_script_cards(
    run_id: str,
    settings: Settings = Depends(get_settings),
    store: RunStore = Depends(get_run_store),
) -> ChapterScriptReviewsResponse:
    try:
        manifest = store.read_manifest(run_id)
        _assert_manifest_status(
            manifest.status,
            {RunStatus.awaiting_script_review},
            "Run is not awaiting chapter script review.",
        )
        AdaptationWorkflow(settings, store).approve_all_chapter_scripts(run_id)
        return _chapter_script_reviews_response(run_id, store)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/runs/{run_id}/chapter-script-cards/{chapter_id}/regenerate",
    response_model=ChapterScriptReviewsResponse,
)
def regenerate_chapter_script_card(
    run_id: str,
    chapter_id: str,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    store: RunStore = Depends(get_run_store),
) -> ChapterScriptReviewsResponse:
    try:
        manifest = store.read_manifest(run_id)
        _assert_manifest_status(
            manifest.status,
            {RunStatus.awaiting_script_review},
            "Run is not awaiting chapter script review.",
        )
        feedback = _latest_script_feedback(run_id, store, chapter_id)
        _mark_chapter_script_review_regenerating(run_id, store, chapter_id)
        store.set_stage(
            run_id,
            "regenerate_chapter_script",
            "running",
            message=f"Regenerating script card {chapter_id}.",
            run_status=RunStatus.regenerating_chapter_script,
        )
        background_tasks.add_task(
            AdaptationWorkflow(settings, store).regenerate_chapter_script,
            run_id,
            chapter_id,
            feedback,
        )
        return _chapter_script_reviews_response(run_id, store)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{run_id}/chapter-script-cards/{chapter_id}/chat/stream")
def chapter_script_chat_stream(
    run_id: str,
    chapter_id: str,
    request: ChapterChatRequest,
    settings: Settings = Depends(get_settings),
    store: RunStore = Depends(get_run_store),
) -> StreamingResponse:
    try:
        response = _chapter_script_reviews_response(run_id, store)
        item = next(
            (candidate for candidate in response.items if candidate.review.chapter_id == chapter_id),
            None,
        )
        if item is None or item.script_card is None:
            raise HTTPException(status_code=404, detail="Chapter script card not found.")
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
    _append_chat_message(run_id, store, user_message, "chapter_script_chat_messages.json")
    _append_script_feedback(
        run_id,
        store,
        ScriptFeedback(
            id=str(uuid4()),
            source="chapter_script_chat",
            target_type="chapter_script",
            target_chapter_id=chapter_id,
            complaint=request.message,
            desired_change="",
            ai_assessment="作者在章节剧本卡聊天中提出了不满意点，可用于重新生成本章剧本卡。",
            created_at=now_iso(),
        ),
    )
    chat_messages = _chat_messages_for_chapter(
        run_id,
        store,
        chapter_id,
        "chapter_script_chat_messages.json",
    )

    def event_stream() -> Iterator[str]:
        yield _sse("visible_thinking", {"content": "我正在对照本章简介卡、剧本卡和你的反馈，整理可执行的重写方向。"})
        answer = _chapter_script_discussion_answer(
            settings,
            item.chapter,
            item.source_card,
            item.script_card,
            chat_messages,
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
        _append_chat_message(run_id, store, assistant_message, "chapter_script_chat_messages.json")
        yield _sse("final", {"content": collected})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get(
    "/runs/{run_id}/chapter-script-cards/{chapter_id}/chat/messages",
    response_model=ChapterChatMessagesResponse,
)
def get_chapter_script_chat_messages(
    run_id: str,
    chapter_id: str,
    store: RunStore = Depends(get_run_store),
) -> ChapterChatMessagesResponse:
    try:
        store.read_manifest(run_id)
        raw_messages = store.read_json(run_id, "chapter_script_chat_messages.json")
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


@router.post("/runs/{run_id}/continuity-merge", response_model=CreateRunResponse)
def continuity_merge(
    run_id: str,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    store: RunStore = Depends(get_run_store),
) -> CreateRunResponse:
    try:
        manifest = store.read_manifest(run_id)
        if manifest.status in {RunStatus.merging_continuity, RunStatus.awaiting_final_review}:
            return CreateRunResponse(run_id=manifest.run_id, status=manifest.status)
        _assert_manifest_status(
            manifest.status,
            {RunStatus.awaiting_script_review},
            "Run is not awaiting chapter script review.",
        )
        _assert_script_reviews_approved(run_id, store)
        manifest = store.set_stage(
            manifest.run_id,
            "continuity_merge",
            "running",
            message="Merging approved chapter script cards into one coherent script.",
            run_status=RunStatus.merging_continuity,
        )
        background_tasks.add_task(AdaptationWorkflow(settings, store).continuity_merge, manifest.run_id)
        return CreateRunResponse(run_id=manifest.run_id, status=manifest.status)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{run_id}/final-feedback", response_model=FinalFeedbackResponse)
def create_final_feedback(
    run_id: str,
    request: FinalFeedbackRequest,
    settings: Settings = Depends(get_settings),
    store: RunStore = Depends(get_run_store),
) -> FinalFeedbackResponse:
    try:
        _assert_final_review_ready(run_id, store)
        workflow = AdaptationWorkflow(settings, store)
        feedback = workflow.create_final_feedback(
            run_id,
            request.category,
            request.complaint,
            request.desired_change,
        )
        return FinalFeedbackResponse(
            feedback=feedback,
            suggested_chapter_id=feedback.target_chapter_id,
            suggested_scene_id=feedback.target_scene_id,
            message=feedback.ai_assessment,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{run_id}/final-feedback/chat/stream")
def final_feedback_chat_stream(
    run_id: str,
    request: FinalFeedbackRequest,
    settings: Settings = Depends(get_settings),
    store: RunStore = Depends(get_run_store),
) -> StreamingResponse:
    try:
        _assert_final_review_ready(run_id, store)
        workflow = AdaptationWorkflow(settings, store)
        feedback = workflow.create_final_feedback(
            run_id,
            request.category,
            request.complaint,
            request.desired_change,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user_message = ChapterChatMessage(
        id=str(uuid4()),
        chapter_id="final",
        role="user",
        content=(
            f"返修类型：{request.category}\n"
            f"不满意点：{request.complaint}\n"
            f"希望调整：{request.desired_change or '未填写'}"
        ),
        created_at=now_iso(),
    )
    _append_chat_message(run_id, store, user_message, "final_feedback_chat_messages.json")

    def event_stream() -> Iterator[str]:
        yield _sse("visible_thinking", {"content": "我正在判断这是跨章连贯问题，还是某一章剧本卡需要返修。"})
        if feedback.target_type == "continuity":
            answer = (
                "我判断这更像连贯性问题：前面单章你已经通过，最终不满意主要发生在合成后的顺序、过渡、"
                "人物动机承接或线索节奏上。建议保留每章剧本卡，只从连贯性合成阶段恢复，带上你的反馈重新合成。"
            )
        elif feedback.target_type == "chapter_and_continuity":
            answer = (
                f"我判断这是章节剧本卡和连贯性都要调整的问题，最可能先落在 {feedback.target_chapter_id or '某一章'}"
                f"{' / ' + feedback.target_scene_id if feedback.target_scene_id else ''}。"
                "我会先带着你的反馈重写该章剧本卡，再自动重新做连贯性合成，避免只改单章后前后仍然不顺。"
            )
        else:
            answer = (
                f"我判断这更像具体剧本点问题，最可能对应 {feedback.target_chapter_id or '某一章'}"
                f"{' / ' + feedback.target_scene_id if feedback.target_scene_id else ''}。"
                "我会先重写这一章剧本卡，其他章节保持不变，再自动重新做连贯性合成。"
            )
        if request.desired_change:
            answer += f" 我会把你的调整方向记入返修提示：{request.desired_change}"
        chunks = [answer[index : index + 30] for index in range(0, len(answer), 30)]
        collected = ""
        for chunk in chunks:
            collected += chunk
            yield _sse("assistant_delta", {"content": chunk})
        assistant_message = ChapterChatMessage(
            id=str(uuid4()),
            chapter_id="final",
            role="assistant",
            content=collected,
            created_at=now_iso(),
        )
        _append_chat_message(run_id, store, assistant_message, "final_feedback_chat_messages.json")
        yield _sse(
            "final_feedback",
            {
                "feedback": feedback.model_dump(mode="json"),
                "suggested_chapter_id": feedback.target_chapter_id,
                "suggested_scene_id": feedback.target_scene_id,
                "message": feedback.ai_assessment,
            },
        )
        yield _sse("final", {"content": collected})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/runs/{run_id}/final-feedback/{feedback_id}/apply", response_model=FinalFeedbackResponse)
def apply_final_feedback(
    run_id: str,
    feedback_id: str,
    request: ApplyFinalFeedbackRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    store: RunStore = Depends(get_run_store),
) -> FinalFeedbackResponse:
    try:
        _assert_final_review_ready(run_id, store)
        workflow = AdaptationWorkflow(settings, store)
        feedback = next(
            (
                item
                for item in workflow._read_feedback(run_id)  # noqa: SLF001 - internal light-state helper for API response.
                if item.id == feedback_id
            ),
            None,
        )
        if feedback is None:
            raise HTTPException(status_code=404, detail="Feedback not found.")
        confirmed_chapter_id = request.confirmed_chapter_id
        if feedback.target_type != "continuity" and not request.confirmed_chapter_id:
            raise HTTPException(
                status_code=409,
                detail="Confirm the target chapter before applying this feedback.",
            )
        if feedback.target_type != "continuity":
            script_cards = _chapter_script_reviews_response(run_id, store).items
            script_card_ids = {
                item.review.chapter_id
                for item in script_cards
                if item.script_card is not None
            }
            if confirmed_chapter_id not in script_card_ids:
                raise HTTPException(
                    status_code=409,
                    detail="Confirmed chapter script card does not exist.",
                )
        background_tasks.add_task(
            workflow.apply_final_feedback,
            run_id,
            feedback_id,
            confirmed_chapter_id,
        )
        return FinalFeedbackResponse(
            feedback=feedback,
            suggested_chapter_id=confirmed_chapter_id,
            suggested_scene_id=feedback.target_scene_id,
            message=(
                "已开始带着反馈重新做连贯性合成。"
                if feedback.target_type == "continuity"
                else "已开始重写目标章节剧本卡，完成后会自动重新做连贯性合成。"
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{run_id}/final-confirm", response_model=RunStatusResponse)
def confirm_final_script(
    run_id: str,
    store: RunStore = Depends(get_run_store),
) -> RunStatusResponse:
    try:
        manifest = store.read_manifest(run_id)
        if manifest.status != RunStatus.awaiting_final_review:
            raise HTTPException(status_code=409, detail="Run is not awaiting final review.")
        if "script.yaml" not in manifest.artifacts:
            raise HTTPException(status_code=409, detail="Final YAML is not ready.")
        manifest = store.succeed(run_id)
        return RunStatusResponse(
            run_id=manifest.run_id,
            status=manifest.status,
            current_stage=manifest.current_stage,
            stages=manifest.stages,
            artifacts=manifest.artifacts,
            error=manifest.error,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc


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


def _chapter_script_reviews_response(run_id: str, store: RunStore) -> ChapterScriptReviewsResponse:
    chapters = [Chapter.model_validate(item) for item in store.read_json(run_id, "chapters.json")]
    try:
        source_cards = [
            ChapterCard.model_validate(item)
            for item in store.read_json(run_id, "chapter_cards.json")
        ]
    except Exception:
        source_cards = []
    try:
        script_cards = [
            ChapterScriptCard.model_validate(item)
            for item in store.read_json(run_id, "chapter_script_cards.json")
        ]
    except Exception:
        script_cards = []
    try:
        reviews = [
            ChapterScriptReview.model_validate(item)
            for item in store.read_json(run_id, "chapter_script_reviews.json")
        ]
    except Exception:
        reviews = []
    source_cards_by_id = {card.chapter_id: card for card in source_cards}
    script_cards_by_id = {card.chapter_id: card for card in script_cards}
    reviews_by_id = {review.chapter_id: review for review in reviews}
    review_ids = set(reviews_by_id) or set(script_cards_by_id)
    items = []
    for chapter in chapters:
        chapter_id = f"ch_{chapter.index:03d}"
        if review_ids and chapter_id not in review_ids:
            continue
        items.append(
            ChapterScriptReviewItem(
                chapter=chapter,
                source_card=source_cards_by_id.get(chapter_id),
                script_card=script_cards_by_id.get(chapter_id),
                review=reviews_by_id.get(chapter_id) or ChapterScriptReview(chapter_id=chapter_id),
            )
        )
    return ChapterScriptReviewsResponse(run_id=run_id, items=items)


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


def _assert_generation_scope_approved(
    run_id: str,
    store: RunStore,
    generation_scope: list[int],
) -> None:
    reviews = _chapter_reviews_response(run_id, store)
    approved_indexes = {
        item.chapter.index
        for item in reviews.items
        if item.review.status == "approved" and item.card is not None
    }
    blocked = [index for index in generation_scope if index not in approved_indexes]
    if blocked:
        raise HTTPException(
            status_code=409,
            detail=f"Selected chapters are not approved or do not exist: {blocked}.",
        )


def _assert_script_reviews_approved(run_id: str, store: RunStore) -> None:
    reviews = _chapter_script_reviews_response(run_id, store)
    blocked = [
        item.review.chapter_id
        for item in reviews.items
        if item.review.status != "approved" or item.script_card is None
    ]
    if not reviews.items:
        raise HTTPException(
            status_code=409,
            detail="Chapter script cards must be generated before continuity merge.",
        )
    if blocked:
        raise HTTPException(
            status_code=409,
            detail="All chapter script cards must be approved before continuity merge.",
        )


def _assert_final_review_ready(run_id: str, store: RunStore) -> None:
    manifest = store.read_manifest(run_id)
    if manifest.status != RunStatus.awaiting_final_review or "script.yaml" not in manifest.artifacts:
        raise HTTPException(
            status_code=409,
            detail="Final feedback is only available while the run is awaiting final review.",
        )


def _append_chat_message(
    run_id: str,
    store: RunStore,
    message: ChapterChatMessage,
    artifact: str = "chapter_chat_messages.json",
) -> None:
    try:
        messages = list(store.read_json(run_id, artifact))
    except Exception:
        messages = []
    messages.append(message.model_dump(mode="json"))
    store.write_json(run_id, artifact, messages)


def _chat_messages_for_chapter(
    run_id: str,
    store: RunStore,
    chapter_id: str,
    artifact: str = "chapter_chat_messages.json",
) -> list[ChapterChatMessage]:
    try:
        raw_messages = store.read_json(run_id, artifact)
    except Exception:
        return []
    messages = []
    for item in raw_messages:
        try:
            message = ChapterChatMessage.model_validate(item)
        except Exception:
            continue
        if message.chapter_id == chapter_id:
            messages.append(message)
    return messages


def _discussion_notes(
    run_id: str,
    store: RunStore,
    chapter_id: str,
    artifact: str,
) -> str:
    messages = _chat_messages_for_chapter(run_id, store, chapter_id, artifact)
    if not messages:
        return ""
    lines = []
    for message in messages[-10:]:
        label = "作者" if message.role == "user" else "AI"
        lines.append(f"{label}: {_compact_text(message.content, 360)}")
    return "\n".join(lines)


def _chapter_discussion_answer(
    settings: Settings,
    chapter: Chapter,
    card: ChapterCard,
    messages: list[ChapterChatMessage],
) -> str:
    latest_user = next((message.content for message in reversed(messages) if message.role == "user"), "")
    client = LlmClient(settings)
    if client.mock:
        return (
            f"我理解你是在确认《{chapter.title}》这张理解卡有没有读偏。"
            f"当前卡片把本章概括为：{card.summary} "
            f"你刚才提到的是：{latest_user or '还没有明确的不满点'}。"
            "我建议先核对三件事：人物动机有没有被说准、关键线索有没有漏掉、心理描写是不是需要更具体地外化。"
            "如果你确认问题点，我会把这段讨论作为重读提示，重新生成这一章理解卡。"
        )
    try:
        return client.generate_text(
            (
                "你是小说改编副编剧，正在和作者讨论某一章的 AI 理解卡是否读准。"
                "请像真实创作伙伴一样回应，不要机械重复按钮说明。"
                "你需要先判断作者的不满可能指向哪里，再结合原文和当前理解卡给出具体分析。"
                "如果作者表达不够明确，最多追问两个很具体的问题。"
                "如果已经能判断问题，就提炼一段可用于重新理解本章的修改方向。"
                "不要展示隐藏推理链，不要编造原文没有支持的信息，回复使用简体中文。"
            ),
            {
                "chapter": {
                    "chapter_id": f"ch_{chapter.index:03d}",
                    "title": chapter.title,
                    "text": chapter.text[:8000],
                },
                "current_chapter_card": card.model_dump(mode="json"),
                "chat_history": [
                    {
                        "role": "作者" if message.role == "user" else "AI",
                        "content": message.content,
                    }
                    for message in messages[-12:]
                ],
                "expected_output": (
                    "给作者一段自然语言回复，说明你如何理解他的疑虑；"
                    "指出本章理解卡可能需要校正的地方；必要时追问；"
                    "最后用一句话说明确认后可以带着这段讨论重新理解。"
                ),
            },
        )
    except Exception as exc:
        return (
            "真实模型这次没有成功返回完整讨论回复，但我已经记录了你的反馈。"
            f"当前可用于重读的疑虑是：{latest_user or str(exc)}"
        )


def _chapter_script_discussion_answer(
    settings: Settings,
    chapter: Chapter,
    source_card: ChapterCard | None,
    script_card: ChapterScriptCard,
    messages: list[ChapterChatMessage],
) -> str:
    latest_user = next((message.content for message in reversed(messages) if message.role == "user"), "")
    client = LlmClient(settings)
    if client.mock:
        return (
            f"我理解你是在检查《{chapter.title}》这张剧本卡是否符合预期。"
            f"当前剧本卡摘要是：{script_card.summary} "
            f"你指出的问题是：{latest_user or '还没有明确的不满点'}。"
            "我会优先判断问题属于对白、动作、冲突、人物动机还是前后衔接。"
            "确认后点“重写本章剧本卡”，系统会只重写这一章，再回到连贯性合成。"
        )
    try:
        return client.generate_text(
            (
                "你是小说改编副编剧，正在和作者讨论某一章剧本卡为什么不合适。"
                "请不要只建议点击按钮，而要帮助作者定位问题：对白、动作、冲突、节奏、人物动机、"
                "场景可拍性或前后衔接。"
                "请结合章节原文、章节理解卡、当前剧本卡和聊天历史，给出可执行的重写方向。"
                "如果定位不明确，最多追问两个具体问题。回复使用简体中文。"
            ),
            {
                "chapter": {
                    "chapter_id": f"ch_{chapter.index:03d}",
                    "title": chapter.title,
                    "text": chapter.text[:8000],
                },
                "chapter_card": source_card.model_dump(mode="json") if source_card else None,
                "current_script_card": script_card.model_dump(mode="json"),
                "chat_history": [
                    {
                        "role": "作者" if message.role == "user" else "AI",
                        "content": message.content,
                    }
                    for message in messages[-12:]
                ],
            },
        )
    except Exception as exc:
        return (
            "真实模型这次没有成功返回完整讨论回复，但我已经记录了你的反馈。"
            f"当前可用于重写的疑虑是：{latest_user or str(exc)}"
        )


def _latest_script_feedback(
    run_id: str,
    store: RunStore,
    chapter_id: str,
) -> ScriptFeedback | None:
    try:
        raw_feedbacks = store.read_json(run_id, "chapter_script_feedback.json")
    except Exception:
        return None
    feedbacks = []
    for item in raw_feedbacks:
        try:
            feedback = ScriptFeedback.model_validate(item)
        except Exception:
            continue
        if feedback.target_chapter_id == chapter_id:
            feedbacks.append(feedback)
    return feedbacks[-1] if feedbacks else None


def _compact_text(value: str, limit: int = 240) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _append_script_feedback(
    run_id: str,
    store: RunStore,
    feedback: ScriptFeedback,
) -> None:
    try:
        feedbacks = list(store.read_json(run_id, "chapter_script_feedback.json"))
    except Exception:
        feedbacks = []
    feedbacks.append(feedback.model_dump(mode="json"))
    store.write_json(run_id, "chapter_script_feedback.json", feedbacks)


def _sse(event_type: str, payload: dict[str, object]) -> str:
    return "data: " + json.dumps({"type": event_type, **payload}, ensure_ascii=False) + "\n\n"
