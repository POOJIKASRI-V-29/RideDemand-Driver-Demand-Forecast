"""The trained-model path, exercised against the real artifact when present.

These tests are skipped on a checkout that has not run the training pipeline
yet, so the suite stays runnable before any data is prepared.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from app.config import settings
from app.ml.features import STAT_COLUMNS, attach_features, compute_stats
from app.ml.model import BASELINE_COLUMN, FEATURE_NAMES, combine, load_model


@pytest.fixture(scope="module")
def trained_model():
    if not settings.model_path.exists():
        pytest.skip("No trained model; run scripts/train_model.py first.")
    return load_model(settings.model_path)


def test_predictions_are_non_negative_and_finite(trained_model):
    frame = pd.DataFrame(
        {
            "hour": [19, 3, 8],
            "day_of_week": [4, 4, 0],
            "is_weekend": [0, 0, 0],
            "grid_lat": [40.75, 40.75, 40.72],
            "grid_lng": [-73.99, -73.99, -74.0],
            "zone_hour_mean": [110.0, 2.0, 0.0],
            "zone_hour_median": [108.0, 2.0, 0.0],
            "zone_hourofday_mean": [100.0, 2.5, 0.5],
            "zone_dow_mean": [40.0, 40.0, 12.0],
            "zone_mean": [38.0, 38.0, 11.0],
            "zone_recent_hour_mean": [115.0, 2.2, 0.4],
        }
    )
    predictions = trained_model.predict(frame)

    assert len(predictions) == 3
    assert np.all(np.isfinite(predictions))
    assert np.all(predictions >= 0.0)


def test_a_busy_slot_outranks_a_quiet_one(trained_model):
    frame = pd.DataFrame(
        {
            "hour": [19, 4],
            "day_of_week": [4, 4],
            "is_weekend": [0, 0],
            "grid_lat": [40.75, 40.75],
            "grid_lng": [-73.99, -73.99],
            "zone_hour_mean": [110.0, 1.0],
            "zone_hour_median": [108.0, 1.0],
            "zone_hourofday_mean": [100.0, 1.2],
            "zone_dow_mean": [40.0, 40.0],
            "zone_mean": [38.0, 38.0],
            "zone_recent_hour_mean": [115.0, 1.1],
        }
    )
    busy, quiet = trained_model.predict(frame)
    assert busy > quiet


def test_the_saved_feature_order_matches_the_code(trained_model):
    assert trained_model.feature_names == FEATURE_NAMES


def test_combine_clips_negative_corrections_at_zero():
    baseline = np.array([5.0, 0.5, 10.0])
    residual = np.array([-2.0, -4.0, 3.0])
    assert list(combine(baseline, residual)) == [3.0, 0.0, 13.0]


def test_saved_metrics_are_real_numbers_not_placeholders():
    if not settings.metrics_path.exists():
        pytest.skip("No metrics file; run scripts/train_model.py first.")
    metrics = json.loads(settings.metrics_path.read_text())

    for key in ("mae", "rmse", "baseline_mae"):
        assert metrics[key] > 0
    assert 0.0 <= metrics["r2"] <= 1.0
    assert metrics["n_test_rows"] > 0
    # The evaluation split must sit strictly after the training split.
    assert metrics["train_end"] < metrics["test_start"]


def test_stats_are_derived_only_from_the_rows_they_are_given():
    """compute_stats must produce every column the serving path reads back."""
    panel = pd.DataFrame(
        {
            "zone_id": [1, 1, 1, 2],
            "obs_date": pd.to_datetime(
                ["2014-04-04", "2014-04-11", "2014-04-18", "2014-04-04"]
            ),
            "hour": [19, 19, 19, 19],
            "day_of_week": [4, 4, 4, 4],
            "ride_count": [10.0, 20.0, 30.0, 4.0],
        }
    )
    stats = compute_stats(panel, recent_window_days=7)

    assert list(stats.columns) == STAT_COLUMNS
    zone_one = stats[stats["zone_id"] == 1].iloc[0]
    assert zone_one["mean_demand"] == pytest.approx(20.0)
    assert zone_one["median_demand"] == pytest.approx(20.0)
    assert zone_one["sample_count"] == 3

    featured = attach_features(panel, stats)
    assert BASELINE_COLUMN in featured.columns
    assert not featured[FEATURE_NAMES[5:]].isna().any().any()


# --- model artifact caching -------------------------------------------------


def test_a_model_written_after_startup_is_picked_up(tmp_path, monkeypatch):
    """The API is documented as starting before the pipeline runs.

    If the cache latched onto "no model" at startup, such a process would serve
    the historical baseline until someone restarted it.
    """
    from app.config import settings as live_settings
    from app.services import demand_service

    if not settings.model_path.exists():
        pytest.skip("No trained artifact; run scripts/train_model.py first.")
    # Read the real artifact before redirecting model_path at the temp copy.
    trained_bytes = settings.model_path.read_bytes()

    artifact = tmp_path / "demand_model.joblib"
    monkeypatch.setattr(type(live_settings), "model_path", property(lambda _: artifact))
    demand_service.reset_model_cache()
    try:
        assert demand_service.get_model() is None  # nothing trained yet

        artifact.write_bytes(trained_bytes)

        assert demand_service.get_model() is not None  # no restart needed
    finally:
        demand_service.reset_model_cache()


def test_a_removed_model_falls_back_to_the_baseline(tmp_path, monkeypatch):
    from app.config import settings as live_settings
    from app.services import demand_service

    if not settings.model_path.exists():
        pytest.skip("No trained artifact; run scripts/train_model.py first.")
    trained_bytes = settings.model_path.read_bytes()

    artifact = tmp_path / "demand_model.joblib"
    artifact.write_bytes(trained_bytes)
    monkeypatch.setattr(type(live_settings), "model_path", property(lambda _: artifact))
    demand_service.reset_model_cache()
    try:
        assert demand_service.get_model() is not None
        artifact.unlink()
        assert demand_service.get_model() is None
    finally:
        demand_service.reset_model_cache()
