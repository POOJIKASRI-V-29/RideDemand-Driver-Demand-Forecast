"""Feature construction and model persistence.

Shared by the trainer and the API so both build features identically — a
mismatch here is the classic source of silently wrong predictions.

The estimator does not predict demand directly. It predicts the *residual*
against ``zone_hour_mean``, the historical average for that (zone, weekday,
hour) slot:

    predicted_demand = max(0, zone_hour_mean + estimator(features))

That historical average is already a strong predictor for aggregated count
data, and asking a gradient booster to correct it beats asking it to reproduce
it from scratch. ``scripts/train_model.py`` measures both, so the value the
model actually adds is visible rather than assumed.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

# Order matters: the estimator is fitted on this exact column order.
FEATURE_NAMES: list[str] = [
    "hour",
    "day_of_week",
    "is_weekend",
    "grid_lat",
    "grid_lng",
    "zone_hour_mean",
    "zone_hour_median",
    "zone_hourofday_mean",
    "zone_dow_mean",
    "zone_mean",
    "zone_recent_hour_mean",
]

BASELINE_COLUMN = "zone_hour_mean"
TARGET_DESCRIPTION = "residual of ride_count against zone_hour_mean"


def build_features(frame: pd.DataFrame) -> np.ndarray:
    """Return the model matrix for a frame that already carries every feature."""
    missing = [c for c in FEATURE_NAMES if c not in frame.columns]
    if missing:
        raise KeyError(f"Missing feature columns: {missing}")
    return frame[FEATURE_NAMES].to_numpy(dtype=float)


def combine(baseline: np.ndarray, residual: np.ndarray) -> np.ndarray:
    """Baseline plus predicted correction, clipped at zero (counts are >= 0)."""
    return np.clip(np.asarray(baseline, dtype=float) + residual, 0.0, None)


@dataclass(frozen=True)
class LoadedModel:
    estimator: Any
    feature_names: list[str]
    metrics: dict[str, Any]

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        residual = self.estimator.predict(build_features(frame))
        return combine(frame[BASELINE_COLUMN].to_numpy(dtype=float), residual)

    def predict_baseline(self, frame: pd.DataFrame) -> np.ndarray:
        """The historical-average fallback, used when no model file is present."""
        return np.clip(frame[BASELINE_COLUMN].to_numpy(dtype=float), 0.0, None)


def save_model(path: Path, estimator: Any, metrics: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "estimator": estimator,
            "feature_names": FEATURE_NAMES,
            "target": TARGET_DESCRIPTION,
            "metrics": metrics,
        },
        path,
    )


def load_model(path: Path) -> LoadedModel:
    bundle = joblib.load(path)
    return LoadedModel(
        estimator=bundle["estimator"],
        feature_names=bundle["feature_names"],
        metrics=bundle.get("metrics", {}),
    )
