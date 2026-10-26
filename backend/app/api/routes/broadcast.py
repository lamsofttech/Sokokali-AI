import asyncio
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from app.api.deps import get_container
from app.core.container import Container
from app.core.security import require_admin, token_is_valid
from app.integrations.live.base import LiveSourceUnavailableError
from app.schemas.live import BroadcastStatus, LiveEvent
from app.services.gamification import GamificationStatus

router = APIRouter(tags=["broadcast"])

ContainerDep = Annotated[Container, Depends(get_container)]
Admin = [Depends(require_admin)]


@router.get("/api/v1/broadcast/status", response_model=BroadcastStatus, summary="Broadcast state and live stats")
async def broadcast_status(container: ContainerDep) -> BroadcastStatus:
    return container.broadcast.status()


@router.post(
    "/api/v1/broadcast/start",
    response_model=BroadcastStatus,
    dependencies=Admin,
    summary="Start or resume the live broadcast (admin)",
    responses={409: {"description": "The live source cannot run (e.g. TikTok not authorized)"}},
)
async def broadcast_start(container: ContainerDep) -> BroadcastStatus:
    try:
        return await container.broadcast.start()
    except LiveSourceUnavailableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None


@router.post("/api/v1/broadcast/pause", response_model=BroadcastStatus, dependencies=Admin, summary="Pause (admin)")
async def broadcast_pause(container: ContainerDep) -> BroadcastStatus:
    return await container.broadcast.pause()


@router.post("/api/v1/broadcast/stop", response_model=BroadcastStatus, dependencies=Admin, summary="Stop (admin)")
async def broadcast_stop(container: ContainerDep) -> BroadcastStatus:
    return await container.broadcast.stop()


@router.post(
    "/api/v1/broadcast/segments/{segment}",
    dependencies=Admin,
    summary="Run a segment now: trivia, poll, match_preview, forex, responsible_gambling (admin)",
)
async def broadcast_segment(
    container: ContainerDep,
    segment: Literal["match_preview", "trivia", "forex", "poll", "responsible_gambling"],
) -> dict[str, str]:
    await container.broadcast.run_segment(segment)
    return {"started": segment}


@router.post(
    "/api/v1/live/events",
    dependencies=Admin,
    summary="Inject one live event, e.g. from a platform webhook or for testing (admin)",
)
async def inject_event(container: ContainerDep, event: LiveEvent) -> dict[str, Any]:
    return await container.broadcast.handle_event(event)


@router.get("/api/v1/gamification/status", response_model=GamificationStatus, summary="Milestones, trivia, polls")
async def gamification_status(container: ContainerDep) -> GamificationStatus:
    return container.gamification.status()


@router.websocket("/ws/live")
async def live_socket(
    websocket: WebSocket,
    token: Annotated[str | None, Query(max_length=256)] = None,
) -> None:
    """Live feed of viewer events, Sokokali's replies, game updates and broadcast state.

    Viewer comments are shown to admins only, so the same token as the admin endpoints is required
    (as ?token=...; browsers cannot set headers on WebSockets).
    """
    container: Container = websocket.app.state.container
    if not token_is_valid(container.settings, token):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Admin token required")
        return
    await websocket.accept()
    queue = container.hub.connect()
    try:
        await websocket.send_json(
            {
                "type": "snapshot",
                "data": {
                    "state": container.broadcast.status().model_dump(mode="json"),
                    "gamification": container.gamification.status().model_dump(mode="json"),
                    "recent": container.hub.recent(),
                },
            }
        )

        async def pump() -> None:
            while True:
                await websocket.send_json(await queue.get())

        async def listen() -> None:  # returns (via WebSocketDisconnect) as soon as the client goes away
            while True:
                await websocket.receive_text()

        tasks = {asyncio.create_task(pump()), asyncio.create_task(listen())}
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        container.hub.disconnect(queue)
