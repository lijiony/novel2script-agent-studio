from fastapi import APIRouter

from app.domain.schemas import script_json_schema


router = APIRouter(prefix="/api/schema", tags=["schema"])


@router.get("/script")
def get_script_schema():
    return script_json_schema()
