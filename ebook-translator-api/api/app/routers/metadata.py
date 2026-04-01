from fastapi import APIRouter, Depends

from ..auth import get_auth_context
from ..config import Settings, get_settings
from ..models import EngineInfo, FormatInfo

router = APIRouter(prefix="/v1", tags=["metadata"])


@router.get("/engines", response_model=list[EngineInfo])
async def list_engines(
    _: object = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
) -> list[EngineInfo]:
    catalog = {
        "openai": "OpenAI (ChatGPT)",
        "deepl": "DeepL",
        "google": "Google",
        "deepinfra": "DeepInfra (DeepSeek)",
    }
    return [EngineInfo(id=engine_id, display_name=catalog.get(engine_id, engine_id)) for engine_id in sorted(settings.allowed_engines)]


@router.get("/formats", response_model=FormatInfo)
async def list_formats(
    _: object = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
) -> FormatInfo:
    return FormatInfo(
        input_formats=sorted(settings.allowed_input_formats),
        output_formats=sorted(settings.allowed_output_formats),
    )
