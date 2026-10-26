"""Interface every forex price provider must implement."""

from abc import ABC, abstractmethod
from datetime import datetime

from app.schemas.common import DataFreshness
from app.schemas.forex import Candle, CurrencyPair


class ForexDataError(Exception):
    """Raised when a provider cannot return prices (outage, timeout, bad payload)."""


class ForexDataProvider(ABC):
    name: str
    is_simulated: bool

    @abstractmethod
    async def list_pairs(self) -> list[CurrencyPair]: ...

    @abstractmethod
    async def get_candles(self, symbol: str, timeframe: str = "H1", limit: int = 300) -> list[Candle]:
        """Completed candles ordered oldest first."""

    @abstractmethod
    def data_as_of(self) -> datetime: ...

    async def health_check(self) -> bool:
        return True

    async def aclose(self) -> None:
        """Release network resources (HTTP clients); a no-op for offline providers."""

    def freshness(self) -> DataFreshness:
        return DataFreshness.build(self.name, self.is_simulated, self.data_as_of())
