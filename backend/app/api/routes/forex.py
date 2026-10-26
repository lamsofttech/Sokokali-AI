from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.api.deps import get_container
from app.core.container import Container
from app.schemas.forex import CurrencyPair, ForexSignal, ForexSignalList
from app.services.forex_engine import InsufficientForexDataError, PairNotFoundError

router = APIRouter(prefix="/api/v1/forex", tags=["forex"])


def require_forex_enabled(container: Annotated[Container, Depends(get_container)]) -> Container:
    if not container.settings.forex_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forex analysis is disabled")
    return container


ForexContainer = Annotated[Container, Depends(require_forex_enabled)]


@router.get("/pairs", response_model=list[CurrencyPair], summary="Supported currency pairs")
async def pairs(container: ForexContainer) -> list[CurrencyPair]:
    return await container.forex_provider.list_pairs()


@router.get("/signals", response_model=ForexSignalList, summary="Technical signals for every pair")
async def signals(container: ForexContainer) -> ForexSignalList:
    try:
        return ForexSignalList(signals=await container.forex.signals())
    except InsufficientForexDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get(
    "/signals/{symbol}",
    response_model=ForexSignal,
    summary="Technical signal for one pair (e.g. EURUSD)",
    responses={404: {"description": "Unknown pair"}, 422: {"description": "Not enough data"}},
)
async def signal(
    container: ForexContainer,
    symbol: Annotated[str, Path(min_length=6, max_length=7, pattern=r"^[A-Za-z]{3}[-]?[A-Za-z]{3}$")],
) -> ForexSignal:
    try:
        return await container.forex.signal(symbol)
    except PairNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pair '{symbol}' not supported") from None
    except InsufficientForexDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
