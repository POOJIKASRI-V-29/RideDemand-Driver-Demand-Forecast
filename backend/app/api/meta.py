"""Health, app configuration and model provenance endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.schemas import AppConfigResponse, DAY_NAMES, HealthResponse, LatLng, ModelInfo
from app.services import copilot_service, demand_service

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthResponse, summary="Service health")
def health(db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    """Report what the service can actually do right now.

    ``degraded`` means the API is up but cannot serve predictions — typically
    the data-loading or training scripts have not been run yet.
    """
    database = "ok"
    n_zones = n_obs = 0
    try:
        n_zones, n_obs = demand_service.counts(db)
    except SQLAlchemyError:
        database = "unavailable"

    model_loaded = demand_service.get_model() is not None
    healthy = database == "ok" and n_zones > 0 and n_obs > 0
    return HealthResponse(
        status="ok" if healthy else "degraded",
        database=database,
        model_loaded=model_loaded,
        zones_loaded=n_zones,
        observations_loaded=n_obs,
        llm_copilot=copilot_service.llm_available(),
    )


@router.get("/api/config", response_model=AppConfigResponse, summary="Frontend configuration")
def app_config(db: Annotated[Session, Depends(get_db)]) -> AppConfigResponse:
    """Geography, grid size and selector options, so the client hardcodes none of it."""
    try:
        n_zones, _ = demand_service.counts(db)
    except SQLAlchemyError:
        n_zones = 0
    return AppConfigResponse(
        city_name=settings.city_name,
        grid_size=settings.grid_size,
        map_center=LatLng(lat=settings.map_center_lat, lng=settings.map_center_lng),
        map_default_zoom=settings.map_default_zoom,
        bounds=[
            [settings.bbox_min_lat, settings.bbox_min_lng],
            [settings.bbox_max_lat, settings.bbox_max_lng],
        ],
        days=DAY_NAMES,
        hours=list(range(24)),
        windows=[
            {"value": value, "label": label}
            for value, label in demand_service.WINDOW_LABELS.items()
        ],
        has_model=demand_service.get_model() is not None and n_zones > 0,
        has_llm_copilot=copilot_service.llm_available(),
    )


@router.get("/api/model", response_model=ModelInfo, summary="Model provenance and metrics")
def model_info(db: Annotated[Session, Depends(get_db)]) -> ModelInfo:
    """Every metric here was measured by scripts/train_model.py on a held-out split."""
    return demand_service.model_info(db)
