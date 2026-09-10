"""GET/POST /api/copilot — the plain-language driver briefing."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.params import ForecastParamsDep, no_data
from app.database import get_db
from app.schemas import CopilotRequest, CopilotResponse
from app.services import copilot_service, demand_service

router = APIRouter(prefix="/api", tags=["copilot"])


@router.get("/copilot", response_model=CopilotResponse, summary="Driver briefing (query params)")
def get_copilot(
    params: ForecastParamsDep,
    db: Annotated[Session, Depends(get_db)],
) -> CopilotResponse:
    try:
        return copilot_service.generate(
            db, params.day_of_week, params.hour, params.window
        )
    except demand_service.NoDataError as exc:
        raise no_data(exc) from exc


@router.post("/copilot", response_model=CopilotResponse, summary="Driver briefing (JSON body)")
def post_copilot(
    payload: CopilotRequest,
    db: Annotated[Session, Depends(get_db)],
) -> CopilotResponse:
    """Explain the current forecast in language a driver can act on.

    The text is written from the prediction figures the backend computed; when
    no LLM key is configured the deterministic template answers instead, and
    ``source`` says which one was used.
    """
    try:
        day_of_week = demand_service.parse_day(payload.day)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    try:
        return copilot_service.generate(db, day_of_week, payload.hour, payload.window)
    except demand_service.NoDataError as exc:
        raise no_data(exc) from exc
