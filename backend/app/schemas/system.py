from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, bool]


class ComponentStatus(BaseModel):
    name: str
    status: str
    detail: str


class StatusResponse(BaseModel):
    service: str
    version: str
    environment: str
    started_at: datetime
    uptime_seconds: float
    components: list[ComponentStatus]
