"""GET /api/demand — predicted demand for every grid cell."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.params import ForecastParamsDep, no_data
from app.database import get_db
from app.schemas import DemandResponse
from app.services import demand_service

router = APIRouter(prefix="/api", tags=["demand"])


@router.get("/demand", response_model=DemandResponse, summary="Predicted demand per zone")
def get_demand(
    params: ForecastParamsDep,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[
        int | None,
        Query(ge=1, description="Return only the N busiest zones. Omit for every zone."),
    ] = None,
) -> DemandResponse:
    """Predicted demand for the selected day, hour and forecast window.

    Zones come back sorted by predicted demand, busiest first, together with the
    day's hourly demand profile and a description of the model that produced
    the numbers.
    """
    try:
        zones = demand_service.predict_zones(
            db, params.day_of_week, params.hour, params.window
        )
        profile = demand_service.hourly_profile(db, params.day_of_week)
    except demand_service.NoDataError as exc:
        raise no_data(exc) from exc

    summary = demand_service.build_summary(zones, profile)
    return DemandResponse(
        request=demand_service.request_info(params.day_of_week, params.hour, params.window),
        generated_at=demand_service.now(),
        model_info=demand_service.model_info(db),
        summary=summary,
        zones=zones[:limit] if limit else zones,
        hourly_profile=profile,
    )
