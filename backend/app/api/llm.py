from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.domain.schemas import LlmStatusResponse, LlmTestResponse
from app.services.llm_client import LlmClient


router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/status", response_model=LlmStatusResponse)
def llm_status(settings: Settings = Depends(get_settings)) -> LlmStatusResponse:
    return LlmStatusResponse.model_validate(LlmClient(settings).status())


@router.post("/test", response_model=LlmTestResponse)
def test_llm(settings: Settings = Depends(get_settings)) -> LlmTestResponse:
    return LlmTestResponse.model_validate(LlmClient(settings).test_connection())
