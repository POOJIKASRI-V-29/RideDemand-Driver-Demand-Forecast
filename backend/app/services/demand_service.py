"""Turning a (day, hour, window) request into predicted demand per grid cell.

The whole prediction path lives here so that ``/api/demand``,
``/api/hotspots``, ``/api/recommendation`` and ``/api/copilot`` all answer from
one computation rather than four slightly different ones.
"""
from __future__ import annotations

import threading
from datetime import UTC, datetime
from functools import lru_cache

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.ml.features import stats_to_features
from app.ml.grid import cell_bounds, cell_center
from app.ml.model import BASELINE_COLUMN, FEATURE_NAMES, LoadedModel, load_model
from app.models import ModelMetadata, Zone, ZoneHourStat
from app.schemas import (
    DAY_NAMES,
    DemandLevel,
    ForecastRequestInfo,
    ForecastSummary,
    ForecastWindow,
    HourlyDemandPoint,
    LatLng,
    ModelInfo,
    ZoneDemand,
)

WINDOW_LABELS: dict[int, str] = {
    30: "Next 30 min",
    60: "Next 60 min",
    120: "Next 2 hours",
}

# Bands applied to a zone's demand relative to the busiest zone in the same
# forecast. This is a presentation aid for the map legend, not a confidence.
LEVEL_THRESHOLDS: list[tuple[float, DemandLevel]] = [
    (0.80, "very_high"),
    (0.55, "high"),
    (0.30, "moderate"),
    (0.00, "low"),
]

_model_lock = threading.Lock()
_model: LoadedModel | None = None
_model_mtime: float | None = None


class NoDataError(RuntimeError):
    """Raised when the database holds no zones/statistics to predict from."""


def get_model() -> LoadedModel | None:
    """The trained model, or ``None`` to fall back to the historical baseline.

    The model is cached, keyed on the artifact's modification time, and the
    cheap ``stat`` on each call buys two things that matter operationally:

    * an API started before training finished — the documented Docker order is
      ``up backend`` then run the pipeline — picks the model up as soon as it
      lands, instead of serving the baseline until someone restarts it;
    * retraining is served without a restart.
    """
    global _model, _model_mtime
    try:
        mtime = settings.model_path.stat().st_mtime
    except OSError:
        # No artifact yet (or it was removed): serve the baseline.
        if _model is not None:
            with _model_lock:
                _model, _model_mtime = None, None
        return None

    if _model is not None and _model_mtime == mtime:
        return _model

    with _model_lock:
        if _model is None or _model_mtime != mtime:
            _model = load_model(settings.model_path)
            _model_mtime = mtime
    return _model


def reset_model_cache() -> None:
    """Test hook: force the next call to re-read the model file."""
    global _model, _model_mtime
    with _model_lock:
        _model, _model_mtime = None, None


def parse_day(day: str | int) -> int:
    """Accept 'Friday', 'friday', 'fri' or 0-6 and return the weekday index."""
    if isinstance(day, int) or (isinstance(day, str) and day.isdigit()):
        index = int(day)
        if 0 <= index <= 6:
            return index
        raise ValueError(f"day must be between 0 and 6, got {index}")
    text = str(day).strip().lower()
    for index, name in enumerate(DAY_NAMES):
        if text in (name.lower(), name.lower()[:3]):
            return index
    raise ValueError(f"Unknown day '{day}'. Expected one of {DAY_NAMES} or 0-6.")


def request_info(day_of_week: int, hour: int, window: ForecastWindow) -> ForecastRequestInfo:
    return ForecastRequestInfo(
        day=DAY_NAMES[day_of_week],
        day_of_week=day_of_week,
        hour=hour,
        window_minutes=int(window.value),
        window_label=WINDOW_LABELS[int(window.value)],
        grid_size=settings.grid_size,
    )


def _level_for(intensity: float) -> DemandLevel:
    for threshold, level in LEVEL_THRESHOLDS:
        if intensity >= threshold:
            return level
    return "low"


def _load_zone_frame(db: Session) -> pd.DataFrame:
    rows = db.execute(
        select(
            Zone.id.label("zone_id"),
            Zone.name,
            Zone.grid_lat,
            Zone.grid_lng,
            Zone.grid_size,
            Zone.center_lat,
            Zone.center_lng,
        )
    ).all()
    if not rows:
        raise NoDataError(
            "No zones in the database. Run scripts.prepare_data, scripts.load_db "
            "and scripts.train_model."
        )
    return pd.DataFrame(rows, columns=list(rows[0]._fields))


def _load_stats_frame(db: Session, day_of_week: int, hours: list[int]) -> pd.DataFrame:
    rows = db.execute(
        select(
            ZoneHourStat.zone_id,
            ZoneHourStat.day_of_week,
            ZoneHourStat.hour,
            ZoneHourStat.mean_demand,
            ZoneHourStat.median_demand,
            ZoneHourStat.max_demand,
            ZoneHourStat.sample_count,
            ZoneHourStat.hourofday_mean,
            ZoneHourStat.dow_mean,
            ZoneHourStat.zone_mean_demand,
            ZoneHourStat.recent_hour_mean,
        ).where(
            ZoneHourStat.day_of_week == day_of_week,
            ZoneHourStat.hour.in_(hours),
        )
    ).all()
    if not rows:
        raise NoDataError(
            "No zone_hour_stats in the database. Run scripts.train_model to build them."
        )
    return pd.DataFrame(rows, columns=list(rows[0]._fields))


def _predict_hourly(db: Session, day_of_week: int, hours: list[int]) -> pd.DataFrame:
    """Predicted pickups/hour for every zone, for each requested hour."""
    zones = _load_zone_frame(db)
    stats = stats_to_features(_load_stats_frame(db, day_of_week, hours))
    frame = zones.merge(stats, on="zone_id", how="inner")
    if frame.empty:
        raise NoDataError("No overlapping zones and statistics for the requested slot.")

    frame["is_weekend"] = int(day_of_week >= 5)
    frame = frame.dropna(subset=FEATURE_NAMES)

    model = get_model()
    if model is None:
        frame["predicted_per_hour"] = frame[BASELINE_COLUMN].clip(lower=0.0)
    else:
        frame["predicted_per_hour"] = model.predict(frame)
    return frame


def _hours_for_window(hour: int, window: ForecastWindow) -> list[int]:
    if int(window.value) == 120:
        return sorted({hour, (hour + 1) % 24})
    return [hour]


def _aggregate_window(frame: pd.DataFrame, hour: int, window: ForecastWindow) -> pd.DataFrame:
    """Convert hourly rates into a total for the selected forecast window.

    The source data is aggregated per calendar hour, so:
      * 30 min  -> half the predicted hourly rate (uniform within the hour)
      * 60 min  -> the predicted hourly rate as-is
      * 2 hours -> the selected hour plus the following hour
    This assumption is documented in the README.
    """
    minutes = int(window.value)
    if minutes == 120:
        totals = (
            frame.groupby("zone_id")["predicted_per_hour"].sum().reset_index(name="predicted_demand")
        )
        current = frame[frame["hour"] == hour].drop(columns=["predicted_demand"], errors="ignore")
        merged = current.merge(totals, on="zone_id", how="left")
        return merged
    out = frame[frame["hour"] == hour].copy()
    out["predicted_demand"] = out["predicted_per_hour"] * (minutes / 60.0)
    return out


def _to_zone_demand(frame: pd.DataFrame) -> list[ZoneDemand]:
    max_demand = float(frame["predicted_demand"].max()) if not frame.empty else 0.0
    zones: list[ZoneDemand] = []
    for row in frame.itertuples(index=False):
        intensity = float(row.predicted_demand / max_demand) if max_demand > 0 else 0.0
        center = cell_center(row.grid_lat, row.grid_lng, row.grid_size)
        bounds = cell_bounds(row.grid_lat, row.grid_lng, row.grid_size)
        zones.append(
            ZoneDemand(
                zone_id=int(row.zone_id),
                name=str(row.name),
                grid_lat=float(row.grid_lat),
                grid_lng=float(row.grid_lng),
                grid_size=float(row.grid_size),
                center=LatLng(lat=center[0], lng=center[1]),
                bounds=[list(bounds[0]), list(bounds[1])],
                predicted_demand=round(float(row.predicted_demand), 2),
                predicted_per_hour=round(float(row.predicted_per_hour), 2),
                intensity=round(min(max(intensity, 0.0), 1.0), 4),
                level=_level_for(intensity),
                historical_samples=int(row.sample_count),
                historical_mean_per_hour=round(float(row.zone_hour_mean), 2),
            )
        )
    return zones


def predict_zones(db: Session, day_of_week: int, hour: int, window: ForecastWindow) -> list[ZoneDemand]:
    """Ranked predicted demand for every zone, highest first."""
    hours = _hours_for_window(hour, window)
    hourly = _predict_hourly(db, day_of_week, hours)
    windowed = _aggregate_window(hourly, hour, window)
    zones = _to_zone_demand(windowed)
    return sorted(zones, key=lambda z: z.predicted_demand, reverse=True)


def hourly_profile(db: Session, day_of_week: int) -> list[HourlyDemandPoint]:
    """City-wide predicted demand for each hour of the selected day."""
    frame = _predict_hourly(db, day_of_week, list(range(24)))
    totals = frame.groupby("hour")["predicted_per_hour"].sum()
    return [
        HourlyDemandPoint(hour=int(h), total_demand=round(float(totals.get(h, 0.0)), 2))
        for h in range(24)
    ]


def build_summary(zones: list[ZoneDemand], profile: list[HourlyDemandPoint]) -> ForecastSummary:
    peak = max(profile, key=lambda p: p.total_demand) if profile else None
    return ForecastSummary(
        zone_count=len(zones),
        total_predicted_demand=round(sum(z.predicted_demand for z in zones), 2),
        max_zone_demand=round(zones[0].predicted_demand, 2) if zones else 0.0,
        peak_zone_name=zones[0].name if zones else "—",
        peak_hour=peak.hour if peak else 0,
        peak_hour_demand=peak.total_demand if peak else 0.0,
    )


@lru_cache(maxsize=1)
def _fallback_note() -> str:
    return (
        "No trained model file was found, so predictions are the historical average "
        "demand for the same zone, weekday and hour. Run scripts/train_model.py to "
        "enable the gradient boosting model."
    )


def model_info(db: Session) -> ModelInfo:
    """Describe what produced the numbers, using only measured values."""
    model = get_model()
    metadata = db.execute(
        select(ModelMetadata).order_by(ModelMetadata.trained_at.desc()).limit(1)
    ).scalar_one_or_none()

    if model is None or metadata is None:
        return ModelInfo(
            source="historical_baseline",
            algorithm="historical mean of ride_count by (zone, weekday, hour)",
            target="ride_count",
            features=["zone_id", "day_of_week", "hour"],
            note=_fallback_note(),
        )

    return ModelInfo(
        source="gradient_boosting_model",
        algorithm=metadata.algorithm,
        target=str(model.metrics.get("target", "residual against the historical mean")),
        features=metadata.features.split(","),
        trained_at=metadata.trained_at,
        mae=round(metadata.mae, 4),
        rmse=round(metadata.rmse, 4),
        r2=round(metadata.r2, 4),
        baseline_mae=round(metadata.baseline_mae, 4),
        n_train_rows=metadata.n_train_rows,
        n_test_rows=metadata.n_test_rows,
        n_zones=metadata.n_zones,
        train_start=metadata.train_start,
        train_end=metadata.train_end,
        test_start=metadata.test_start,
        test_end=metadata.test_end,
        dataset_name=metadata.dataset_name,
        grid_size=metadata.grid_size,
    )


def counts(db: Session) -> tuple[int, int]:
    from app.models import DemandObservation

    n_zones = db.execute(select(func.count()).select_from(Zone)).scalar_one()
    n_obs = db.execute(select(func.count()).select_from(DemandObservation)).scalar_one()
    return int(n_zones), int(n_obs)


def now() -> datetime:
    return datetime.now(UTC)
