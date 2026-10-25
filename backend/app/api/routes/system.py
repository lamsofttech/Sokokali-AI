from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.deps import get_container
from app.core.container import Container
from app.schemas.system import ComponentStatus, HealthResponse, ReadinessResponse, StatusResponse

router = APIRouter(tags=["system"])

ContainerDep = Annotated[Container, Depends(get_container)]


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health(container: ContainerDep) -> HealthResponse:
    s = container.settings
    return HealthResponse(status="ok", service=s.app_name, version=s.app_version)


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def ready(container: ContainerDep) -> JSONResponse:
    checks = {"sports_provider": await container.sports_provider.health_check()}
    ok = all(checks.values())
    body = ReadinessResponse(status="ready" if ok else "not_ready", checks=checks)
    return JSONResponse(body.model_dump(), status_code=200 if ok else 503)


@router.get("/api/v1/status", response_model=StatusResponse, summary="Service and component status")
async def service_status(container: ContainerDep) -> StatusResponse:
    s = container.settings
    provider = container.sports_provider
    provider_ok = await provider.health_check()
    now = datetime.now(UTC)
    return StatusResponse(
        service=s.app_name,
        version=s.app_version,
        environment=s.environment,
        started_at=container.started_at,
        uptime_seconds=round((now - container.started_at).total_seconds(), 1),
        components=[
            ComponentStatus(
                name="ai_engine",
                status="ok",
                detail="Rule-based multilingual engine (no LLM configured; Phase 2)",
            ),
            ComponentStatus(
                name="sports_provider",
                status="ok" if provider_ok else "down",
                detail=f"{provider.name} ({'SIMULATED data' if provider.is_simulated else 'live data'})",
            ),
            ComponentStatus(name="prediction_engine", status="ok", detail=container.predictions.model_version),
            ComponentStatus(
                name="conversation_memory",
                status="ok",
                detail=f"in-memory, {len(container.memory)} active conversations",
            ),
        ],
    )
