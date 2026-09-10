"""GET /api/hotspots — the ranked top demand areas."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.params import ForecastParamsDep, no_data
from app.database import get_db
from app.schemas import HotspotsResponse
from app.services import demand_service

router = APIRouter(prefix="/api", tags=["hotspots"])


@router.get("/hotspots", response_model=HotspotsResponse, summary="Ranked top demand areas")
def get_hotspots(
    params: ForecastParamsDep,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100, description="How many areas to return.")] = 8,
) -> HotspotsResponse:
    """The busiest predicted zones, highest demand first.

    Ranking happens here rather than in the client so that the map, the list and
    the recommendation can never disagree with one another.
    """
    try:
        zones = demand_service.predict_zones(
            db, params.day_of_week, params.hour, params.window
        )
    except demand_service.NoDataError as exc:
        raise no_data(exc) from exc

    return HotspotsResponse(
        request=demand_service.request_info(params.day_of_week, params.hour, params.window),
        generated_at=demand_service.now(),
        model_info=demand_service.model_info(db),
        hotspots=zones[:limit],
    )
