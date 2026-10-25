from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.api.deps import get_container
from app.core.container import Container
from app.schemas.sports import FixtureList, Prediction
from app.services.prediction_engine import InsufficientDataError, MatchNotFoundError

router = APIRouter(prefix="/api/v1", tags=["sports"])

ContainerDep = Annotated[Container, Depends(get_container)]


@router.get("/fixtures", response_model=FixtureList, summary="Upcoming fixtures")
async def fixtures(
    container: ContainerDep,
    competition: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> FixtureList:
    provider = container.sports_provider
    return FixtureList(
        fixtures=await provider.get_fixtures(competition=competition, limit=limit),
        freshness=provider.freshness(),
    )


@router.get(
    "/predictions/{match_id}",
    response_model=Prediction,
    summary="Home/draw/away probabilities for a fixture",
    responses={404: {"description": "Unknown match"}, 422: {"description": "Not enough data"}},
)
async def prediction(
    container: ContainerDep,
    match_id: Annotated[str, Path(max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")],
) -> Prediction:
    try:
        return await container.predictions.predict(match_id)
    except MatchNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Match '{match_id}' not found") from None
    except InsufficientDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
