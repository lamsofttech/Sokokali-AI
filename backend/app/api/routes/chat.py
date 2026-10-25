from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import enforce_chat_rate_limit, get_container
from app.core.container import Container
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Send a viewer message to Sokokali",
    dependencies=[Depends(enforce_chat_rate_limit)],
)
async def chat(request: ChatRequest, container: Annotated[Container, Depends(get_container)]) -> ChatResponse:
    max_length = container.settings.chat_max_message_length
    if len(request.message) > max_length:
        raise HTTPException(
            status_code=422,
            detail=f"Message is longer than {max_length} characters",
        )
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="Message is empty")
    return await container.chat.handle(request)
