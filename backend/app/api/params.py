"""Shared query-parameter parsing and error translation for the API."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status

from app.schemas import DAY_NAMES, ForecastWindow
from app.services import demand_service


@dataclass(frozen=True)
class ForecastParams:
    day_of_week: int
    hour: int
    window: ForecastWindow


def forecast_params(
    day: Annotated[
        str,
        Query(description=f"Day of week: a name such as 'Friday', or 0-6 where 0 is Monday. Valid names: {', '.join(DAY_NAMES)}."),
    ] = "Friday",
    hour: Annotated[int, Query(ge=0, le=23, description="Hour of day, 0-23.")] = 19,
    window: Annotated[
        ForecastWindow,
        Query(description="Forecast window in minutes: 30, 60 or 120."),
    ] = ForecastWindow.NEXT_60_MIN,
) -> ForecastParams:
    try:
        day_of_week = demand_service.parse_day(day)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return ForecastParams(day_of_week=day_of_week, hour=hour, window=window)


ForecastParamsDep = Annotated[ForecastParams, Depends(forecast_params)]


def no_data(exc: demand_service.NoDataError) -> HTTPException:
    """The database has not been populated yet — a server-state problem, not a bad request."""
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
