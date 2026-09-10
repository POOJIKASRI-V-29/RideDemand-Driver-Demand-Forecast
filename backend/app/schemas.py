"""Pydantic request/response models — the contract the frontend types mirror."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

DAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


class ForecastWindow(int, Enum):
    """Forecast horizons offered in the UI, in minutes."""

    NEXT_30_MIN = 30
    NEXT_60_MIN = 60
    NEXT_2_HOURS = 120


DemandLevel = Literal["low", "moderate", "high", "very_high"]
PredictionSource = Literal["gradient_boosting_model", "historical_baseline"]


class LatLng(BaseModel):
    lat: float
    lng: float


class ZoneDemand(BaseModel):
    """Predicted demand for one grid cell."""

    zone_id: int
    name: str = Field(description="Approximate nearest-neighbourhood label for the cell.")
    grid_lat: float = Field(description="South-west corner latitude of the cell.")
    grid_lng: float = Field(description="South-west corner longitude of the cell.")
    grid_size: float
    center: LatLng
    bounds: list[list[float]] = Field(
        description="[[south, west], [north, east]] — Leaflet rectangle bounds."
    )
    predicted_demand: float = Field(
        description="Predicted pickups over the selected forecast window."
    )
    predicted_per_hour: float = Field(description="Predicted pickups per hour.")
    intensity: float = Field(
        ge=0.0, le=1.0, description="predicted_demand relative to the busiest zone in this forecast."
    )
    level: DemandLevel = Field(
        description="Banding of `intensity`; a relative label, not a confidence score."
    )
    historical_samples: int = Field(
        description="Number of historical observations behind this zone's slot average."
    )
    historical_mean_per_hour: float = Field(
        description="Historical average pickups/hour for this zone, weekday and hour."
    )


class HourlyDemandPoint(BaseModel):
    hour: int
    total_demand: float = Field(description="Predicted pickups/hour summed over every zone.")


class ForecastRequestInfo(BaseModel):
    day: str
    day_of_week: int = Field(ge=0, le=6, description="0 = Monday.")
    hour: int = Field(ge=0, le=23)
    window_minutes: int
    window_label: str
    grid_size: float


class ModelInfo(BaseModel):
    """Provenance for the numbers in the response. Every metric is measured."""

    source: PredictionSource
    algorithm: str
    target: str
    features: list[str]
    trained_at: datetime | None = None
    mae: float | None = Field(
        default=None, description="Mean absolute error on the held-out test split, rides/hour/zone."
    )
    rmse: float | None = None
    r2: float | None = None
    baseline_mae: float | None = Field(
        default=None, description="MAE of the historical-average baseline on the same split."
    )
    n_train_rows: int | None = None
    n_test_rows: int | None = None
    n_zones: int | None = None
    train_start: date | None = None
    train_end: date | None = None
    test_start: date | None = None
    test_end: date | None = None
    dataset_name: str | None = None
    grid_size: float | None = None
    note: str | None = None


class ForecastSummary(BaseModel):
    zone_count: int
    total_predicted_demand: float
    max_zone_demand: float
    peak_zone_name: str
    peak_hour: int = Field(description="Hour of the selected day with the highest city-wide demand.")
    peak_hour_demand: float


class DemandResponse(BaseModel):
    request: ForecastRequestInfo
    generated_at: datetime
    model_info: ModelInfo
    summary: ForecastSummary
    zones: list[ZoneDemand]
    hourly_profile: list[HourlyDemandPoint]


class HotspotsResponse(BaseModel):
    request: ForecastRequestInfo
    generated_at: datetime
    model_info: ModelInfo
    hotspots: list[ZoneDemand]


class RecommendationReason(BaseModel):
    label: str
    value: str
    detail: str


class RecommendationResponse(BaseModel):
    request: ForecastRequestInfo
    generated_at: datetime
    model_info: ModelInfo
    zone: ZoneDemand
    rank: int
    lead_over_runner_up: float = Field(
        description="Predicted demand minus that of the second-ranked zone, over the window."
    )
    runner_up_name: str | None = None
    share_of_top_zones: float = Field(
        ge=0.0, le=1.0, description="Share of the top-10 zones' combined predicted demand."
    )
    reasons: list[RecommendationReason]


class CopilotRequest(BaseModel):
    day: str = "Friday"
    hour: int = Field(default=19, ge=0, le=23)
    window: ForecastWindow = ForecastWindow.NEXT_60_MIN


class CopilotResponse(BaseModel):
    request: ForecastRequestInfo
    generated_at: datetime
    message: str
    source: Literal["llm", "fallback"] = Field(
        description="'llm' when an LLM produced the text, 'fallback' when the deterministic "
        "template did."
    )
    model: str | None = Field(default=None, description="LLM model id, when one was used.")
    grounded_on: dict[str, float | str] = Field(
        description="The exact prediction figures the text was written from."
    )


class AppConfigResponse(BaseModel):
    """Everything the frontend needs so it hardcodes no geography of its own."""

    city_name: str
    grid_size: float
    map_center: LatLng
    map_default_zoom: int
    bounds: list[list[float]]
    days: list[str]
    hours: list[int]
    windows: list[dict[str, str | int]]
    has_model: bool
    has_llm_copilot: bool


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    model_loaded: bool
    zones_loaded: int
    observations_loaded: int
    llm_copilot: bool
