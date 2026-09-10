"""GET /api/recommendation — where the driver should position themselves."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.params import ForecastParamsDep, no_data
from app.database import get_db
from app.schemas import RecommendationResponse
from app.services import demand_service, recommendation_service

router = APIRouter(prefix="/api", tags=["recommendation"])


@router.get(
    "/recommendation",
    response_model=RecommendationResponse,
    summary="Recommended position for the selected slot",
)
def get_recommendation(
    params: ForecastParamsDep,
    db: Annotated[Session, Depends(get_db)],
) -> RecommendationResponse:
    """The highest-demand zone, with the figures that justify the choice.

    No distance, travel time or confidence score is returned: none of those can
    be derived from this dataset, so none is invented.
    """
    try:
        return recommendation_service.recommend(
            db, params.day_of_week, params.hour, params.window
        )
    except demand_service.NoDataError as exc:
        raise no_data(exc) from exc
