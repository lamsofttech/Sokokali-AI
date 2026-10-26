from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.container import Container, build_container
from app.integrations.forex.simulated import SimulatedForexProvider
from app.integrations.sports.simulated import SimulatedSportsProvider
from app.main import create_app

FIXED_NOW = datetime(2026, 10, 24, 12, tzinfo=UTC)


@pytest.fixture
def settings() -> Settings:
    return Settings(environment="test", log_json=False, log_level="WARNING", llm_provider="none", _env_file=None)


@pytest.fixture
def provider() -> SimulatedSportsProvider:
    return SimulatedSportsProvider(seed=2024, now=FIXED_NOW)


@pytest.fixture
def forex_provider() -> SimulatedForexProvider:
    return SimulatedForexProvider(seed=2024, now=FIXED_NOW)


@pytest.fixture
def container(
    settings: Settings, provider: SimulatedSportsProvider, forex_provider: SimulatedForexProvider
) -> Container:
    return build_container(settings, sports_provider=provider, forex_provider=forex_provider)


@pytest.fixture
def client(settings: Settings, container: Container) -> Iterator[TestClient]:
    with TestClient(create_app(settings, container)) as test_client:
        yield test_client
