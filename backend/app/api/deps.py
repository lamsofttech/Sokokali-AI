from fastapi import HTTPException, Request, status

from app.core.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def enforce_chat_rate_limit(request: Request) -> None:
    container = get_container(request)
    if not await container.chat_rate_limiter.check(client_key(request)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many chat messages. Please slow down.",
            headers={"Retry-After": "60"},
        )
