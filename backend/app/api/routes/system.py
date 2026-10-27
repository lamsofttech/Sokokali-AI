from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

from app.api.deps import get_container
from app.core.container import Container
from app.core.security import require_admin
from app.database.storage import Storage
from app.schemas.system import ComponentStatus, HealthResponse, ReadinessResponse, StatusResponse

router = APIRouter(tags=["system"])


def _ai_status(container: Container) -> ComponentStatus:
    llm = container.llm
    if llm is None:
        return ComponentStatus(name="ai_engine", status="ok", detail="Rule-based engine only (no LLM configured)")
    if not llm.available:
        return ComponentStatus(
            name="ai_engine",
            status="degraded",
            detail=f"Claude {llm.model} paused after: {llm.last_error}; using rule-based fallback",
        )
    return ComponentStatus(
        name="ai_engine",
        status="ok",
        detail=f"Claude {llm.model} (effort {llm.effort}) with rule-based fallback",
    )

ContainerDep = Annotated[Container, Depends(get_container)]


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health(container: ContainerDep) -> HealthResponse:
    s = container.settings
    return HealthResponse(status="ok", service=s.app_name, version=s.app_version)


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def ready(container: ContainerDep) -> JSONResponse:
    checks = {"sports_provider": await container.sports_provider.health_check()}
    if container.storage is not None:
        checks["database"] = await container.storage.healthy()
    if container.redis is not None:
        try:
            checks["redis"] = bool(await container.redis.ping())
        except (RedisError, OSError):
            checks["redis"] = False
    if container.settings.forex_enabled:
        checks["forex_provider"] = await container.forex_provider.health_check()
    ok = all(checks.values())
    body = ReadinessResponse(status="ready" if ok else "not_ready", checks=checks)
    return JSONResponse(body.model_dump(), status_code=200 if ok else 503)


@router.get("/api/v1/status", response_model=StatusResponse, summary="Service and component status")
async def service_status(container: ContainerDep) -> StatusResponse:
    s = container.settings
    provider = container.sports_provider
    provider_ok = await provider.health_check()
    stale_error = getattr(provider, "last_error", None)  # set by network providers serving a cached snapshot
    fx = container.forex_provider
    fx_ok = await fx.health_check()
    now = datetime.now(UTC)
    return StatusResponse(
        service=s.app_name,
        version=s.app_version,
        environment=s.environment,
        started_at=container.started_at,
        uptime_seconds=round((now - container.started_at).total_seconds(), 1),
        components=[
            _ai_status(container),
            ComponentStatus(
                name="sports_provider",
                status="down" if not provider_ok else "degraded" if stale_error else "ok",
                detail=f"{provider.name} ({'SIMULATED data' if provider.is_simulated else 'live data'})"
                + (f"; serving cached data, last refresh failed: {stale_error}" if stale_error else ""),
            ),
            ComponentStatus(name="prediction_engine", status="ok", detail=container.predictions.model_version),
            ComponentStatus(
                name="forex_provider",
                status="disabled" if not s.forex_enabled else "ok" if fx_ok else "down",
                detail=f"{fx.name} ({'SIMULATED data' if fx.is_simulated else 'live data'})",
            ),
            ComponentStatus(
                name="forex_signal_engine",
                status="ok" if s.forex_enabled else "disabled",
                detail=f"{container.forex.model_version}; trade levels "
                f"{'ENABLED' if s.forex_trade_levels_enabled else 'disabled pending licensing review'}",
            ),
            ComponentStatus(
                name="broadcast",
                status="degraded" if container.broadcast.source_error else container.broadcast.state.value,
                detail=f"live source: {container.broadcast.source.name}"
                + (" (SIMULATED viewers)" if container.broadcast.source.is_simulated else "")
                + (f"; {container.broadcast.source_error}" if container.broadcast.source_error else ""),
            ),
            ComponentStatus(
                name="database",
                status="ok" if container.storage is not None else "disabled",
                detail="PostgreSQL: predictions, broadcast log and engagement are saved"
                if container.storage is not None
                else "not configured: nothing is saved across restarts",
            ),
            ComponentStatus(
                name="redis",
                status="ok" if container.redis is not None else "disabled",
                detail="shared rate limits" if container.redis is not None else "not configured: in-memory rate limits",
            ),
            ComponentStatus(
                name="conversation_memory",
                status="ok",
                detail=f"in-memory, {len(container.memory)} active conversations",
            ),
        ],
    )


@router.get("/metrics", summary="Prometheus metrics (admin outside development)", dependencies=[Depends(require_admin)])
async def metrics(container: ContainerDep) -> Response:
    m = container.metrics
    m.live_queue.set(len(container.broadcast.pipeline))
    m.ws_clients.set(container.hub.client_count)
    m.broadcast_running.set(1 if container.broadcast.state.value == "running" else 0)
    m.broadcast_errors.set(container.broadcast.errors)
    return Response(m.render(), media_type="text/plain; version=0.0.4; charset=utf-8")


_PREDICTION_FIELDS = (
    "match_id", "home_team", "away_team", "kickoff", "predicted_at", "data_as_of",
    "data_source", "is_simulated", "home_win", "draw", "away_win", "model_version",
)


def _storage(container: Container) -> Storage:
    if container.storage is None:
        raise HTTPException(503, "No database configured (set SOKOKALI_DATABASE_URL)")
    return container.storage


@router.get(
    "/api/v1/history/predictions",
    summary="Stored predictions, newest first (admin)",
    dependencies=[Depends(require_admin)],
)
async def prediction_history(
    container: ContainerDep, limit: Annotated[int, Query(ge=1, le=500)] = 50
) -> list[dict[str, object]]:
    rows = await _storage(container).recent_predictions(limit)
    return [
        {c: getattr(r, c) for c in _PREDICTION_FIELDS}
        for r in rows
    ]


@router.get(
    "/api/v1/history/broadcast",
    summary="What Sokokali said on air, newest first (admin)",
    dependencies=[Depends(require_admin)],
)
async def broadcast_history(
    container: ContainerDep, limit: Annotated[int, Query(ge=1, le=500)] = 50
) -> list[dict[str, object]]:
    rows = await _storage(container).recent_broadcast(limit)
    return [
        {c: getattr(r, c) for c in ("at", "source", "viewer_name", "comment", "reply", "engine")} for r in rows
    ]
