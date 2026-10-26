"""Contracts shared by every market Sokokali covers (sports, forex)."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class DataFreshness(BaseModel):
    source: str = Field(description="Name of the data provider")
    is_simulated: bool = Field(description="True when the data is synthetic and not real-world")
    data_as_of: datetime = Field(description="When the provider data was last refreshed")
    age_seconds: float = Field(ge=0)

    @classmethod
    def build(cls, source: str, is_simulated: bool, data_as_of: datetime) -> "DataFreshness":
        return cls(
            source=source,
            is_simulated=is_simulated,
            data_as_of=data_as_of,
            age_seconds=max(0.0, (datetime.now(UTC) - data_as_of).total_seconds()),
        )
