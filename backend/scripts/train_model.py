"""Train the demand model and record its measured performance.

Pipeline
--------
1. Read zones and observations from PostgreSQL.
2. Expand to a dense panel: every (zone, date, hour) slot, with the hours that
   saw no pickups filled in as 0. Those zeros are real signal — a quiet cell at
   4am is exactly what the model has to learn.
3. Split chronologically: the earliest 80% of dates train, the most recent 20%
   test. A random split would leak future information into the past.
4. Derive the historical-demand aggregates from the TRAINING dates only, so no
   test-period information reaches the model.
5. Select the estimator configuration on an inner validation split carved out
   of the training dates — the test split is never used for any choice.
6. Refit the chosen configuration on the full training split and measure
   MAE / RMSE / R2 on the untouched test split, alongside the MAE of the plain
   historical-average baseline.
7. Persist the model, the aggregates and the measured metrics.

Every number this script reports is computed here. None is hard-coded.

    python -m scripts.train_model
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.database import engine, init_db  # noqa: E402
from app.ml.features import STAT_COLUMNS, attach_features, compute_stats  # noqa: E402
from app.ml.model import (  # noqa: E402
    BASELINE_COLUMN,
    FEATURE_NAMES,
    TARGET_DESCRIPTION,
    build_features,
    combine,
    save_model,
)
from scripts.prepare_data import DATASET_NAME  # noqa: E402

ALGORITHM = "sklearn.ensemble.HistGradientBoostingRegressor"

# Candidate configurations. The winner is picked on the inner validation split.
CANDIDATES: list[dict] = [
    {"loss": "absolute_error", "learning_rate": 0.05, "min_samples_leaf": 40, "max_iter": 600},
    {"loss": "absolute_error", "learning_rate": 0.08, "min_samples_leaf": 100, "max_iter": 400},
    {"loss": "squared_error", "learning_rate": 0.05, "min_samples_leaf": 40, "max_iter": 600},
    {"loss": "poisson", "learning_rate": 0.05, "min_samples_leaf": 40, "max_iter": 600},
]


def make_estimator(params: dict) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.12,
        random_state=settings.random_state,
        **params,
    )


def load_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    with engine.connect() as conn:
        zones = pd.read_sql(
            text("SELECT id AS zone_id, grid_lat, grid_lng, name, total_pickups FROM zones"),
            conn,
        )
        observations = pd.read_sql(
            text("SELECT zone_id, obs_date, hour, ride_count FROM demand_observations"),
            conn,
        )
    if zones.empty or observations.empty:
        raise SystemExit("No data in the database. Run scripts.prepare_data then scripts.load_db.")
    observations["obs_date"] = pd.to_datetime(observations["obs_date"])
    return zones, observations


def build_panel(zones: pd.DataFrame, observations: pd.DataFrame) -> pd.DataFrame:
    """Dense (zone, date, hour) panel with explicit zeros for quiet slots."""
    dates = pd.Index(sorted(observations["obs_date"].unique()), name="obs_date")
    index = pd.MultiIndex.from_product(
        [zones["zone_id"], dates, range(24)], names=["zone_id", "obs_date", "hour"]
    )
    panel = (
        observations.set_index(["zone_id", "obs_date", "hour"])["ride_count"]
        .reindex(index, fill_value=0)
        .reset_index()
    )
    panel["day_of_week"] = panel["obs_date"].dt.dayofweek  # Monday = 0
    panel["is_weekend"] = (panel["day_of_week"] >= 5).astype(int)
    return panel.merge(zones[["zone_id", "grid_lat", "grid_lng"]], on="zone_id", how="left")


def chronological_split(
    panel: pd.DataFrame, test_fraction: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = np.sort(panel["obs_date"].unique())
    cut = min(max(int(len(dates) * (1.0 - test_fraction)), 1), len(dates) - 1)
    split_date = dates[cut]
    return (
        panel[panel["obs_date"] < split_date].copy(),
        panel[panel["obs_date"] >= split_date].copy(),
    )


def fit_residual(estimator, frame: pd.DataFrame):
    target = frame["ride_count"].to_numpy(dtype=float) - frame[BASELINE_COLUMN].to_numpy(dtype=float)
    if estimator.loss == "poisson":
        # Poisson needs a non-negative target, so this candidate learns the
        # count directly rather than the residual.
        target = frame["ride_count"].to_numpy(dtype=float)
    estimator.fit(build_features(frame), target)
    return estimator


def predict(estimator, frame: pd.DataFrame) -> np.ndarray:
    raw = estimator.predict(build_features(frame))
    if estimator.loss == "poisson":
        return np.clip(raw, 0.0, None)
    return combine(frame[BASELINE_COLUMN].to_numpy(dtype=float), raw)


def select_configuration(train: pd.DataFrame) -> dict:
    """Pick a candidate on an inner validation split of the training dates."""
    inner_train, inner_val = chronological_split(train, settings.test_fraction)
    stats = compute_stats(inner_train)
    inner_train = attach_features(inner_train, stats)
    inner_val = attach_features(inner_val, stats)

    y_val = inner_val["ride_count"].to_numpy(dtype=float)
    baseline_mae = mean_absolute_error(y_val, inner_val[BASELINE_COLUMN])
    print(f"  baseline (historical mean)          MAE {baseline_mae:.4f}")

    best, best_mae = None, float("inf")
    for params in CANDIDATES:
        estimator = fit_residual(make_estimator(params), inner_train)
        mae = mean_absolute_error(y_val, predict(estimator, inner_val))
        marker = ""
        if mae < best_mae:
            best, best_mae, marker = params, mae, "  <- best so far"
        label = f"{params['loss']}/lr={params['learning_rate']}/leaf={params['min_samples_leaf']}"
        print(f"  {label:<36}MAE {mae:.4f}{marker}")
    assert best is not None
    return best


def persist_stats(stats: pd.DataFrame) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE zone_hour_stats RESTART IDENTITY"))
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            statement = (
                f"COPY zone_hour_stats ({', '.join(STAT_COLUMNS)}) FROM STDIN WITH (FORMAT CSV)"
            )
            with cur.copy(statement) as copy:
                copy.write(stats[STAT_COLUMNS].to_csv(index=False, header=False))
        raw.commit()
    finally:
        raw.close()


def persist_metadata(metrics: dict) -> None:
    columns = [
        "algorithm",
        "features",
        "n_train_rows",
        "n_test_rows",
        "n_zones",
        "mae",
        "rmse",
        "r2",
        "baseline_mae",
        "train_start",
        "train_end",
        "test_start",
        "test_end",
        "dataset_name",
        "grid_size",
    ]
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM model_metadata"))
        conn.execute(
            text(
                f"INSERT INTO model_metadata ({', '.join(columns)}) "
                f"VALUES ({', '.join(':' + c for c in columns)})"
            ),
            {c: metrics[c] for c in columns},
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--test-fraction", type=float, default=settings.test_fraction,
        help="Share of the most recent dates held out for testing.",
    )
    args = parser.parse_args()

    init_db()

    print("1/7 Reading data from PostgreSQL")
    zones, observations = load_frames()
    print(f"  {len(zones):,} zones, {len(observations):,} non-zero observations")

    print("\n2/7 Building the dense hourly panel")
    panel = build_panel(zones, observations)
    empty_share = (panel["ride_count"] == 0).mean()
    print(f"  {len(panel):,} (zone, date, hour) rows, {empty_share:.1%} with zero pickups")

    print("\n3/7 Chronological train/test split")
    train, test = chronological_split(panel, args.test_fraction)
    print(f"  train {train['obs_date'].min().date()} .. {train['obs_date'].max().date()} ({len(train):,} rows)")
    print(f"  test  {test['obs_date'].min().date()} .. {test['obs_date'].max().date()} ({len(test):,} rows)")

    print("\n4/7 Selecting the estimator on an inner validation split")
    params = select_configuration(train)
    print(f"  chosen: {params}")

    print("\n5/7 Deriving historical aggregates from the training split only")
    stats = compute_stats(train)
    train = attach_features(train, stats)
    test = attach_features(test, stats)
    print(f"  {len(stats):,} (zone, weekday, hour) aggregate rows")

    print(f"\n6/7 Fitting {ALGORITHM} on the full training split")
    estimator = fit_residual(make_estimator(params), train)
    print(f"  target: {TARGET_DESCRIPTION if params['loss'] != 'poisson' else 'ride_count'}")
    print(f"  boosting iterations used: {estimator.n_iter_}")

    print("\n7/7 Evaluating on the held-out test split")
    y_true = test["ride_count"].to_numpy(dtype=float)
    y_pred = predict(estimator, test)
    baseline_pred = np.clip(test[BASELINE_COLUMN].to_numpy(dtype=float), 0.0, None)

    metrics = {
        "algorithm": ALGORITHM,
        "loss": params["loss"],
        "target": TARGET_DESCRIPTION if params["loss"] != "poisson" else "ride_count",
        "features": ",".join(FEATURE_NAMES),
        "n_train_rows": int(len(train)),
        "n_test_rows": int(len(test)),
        "n_zones": int(len(zones)),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred)),
        "baseline_mae": float(mean_absolute_error(y_true, baseline_pred)),
        "train_start": train["obs_date"].min().date(),
        "train_end": train["obs_date"].max().date(),
        "test_start": test["obs_date"].min().date(),
        "test_end": test["obs_date"].max().date(),
        "dataset_name": DATASET_NAME,
        "grid_size": float(settings.grid_size),
    }

    improvement = 1.0 - metrics["mae"] / metrics["baseline_mae"]
    print(f"  MAE          {metrics['mae']:.4f} rides/hour per zone")
    print(f"  RMSE         {metrics['rmse']:.4f}")
    print(f"  R2           {metrics['r2']:.4f}")
    print(f"  Baseline MAE {metrics['baseline_mae']:.4f} (historical mean for the same slot)")
    print(f"  The model improves on the baseline MAE by {improvement:.2%}.")

    persist_stats(stats)
    persist_metadata(metrics)
    save_model(settings.model_path, estimator, metrics)

    settings.metrics_path.parent.mkdir(parents=True, exist_ok=True)
    settings.metrics_path.write_text(
        json.dumps(
            {k: (v.isoformat() if isinstance(v, date) else v) for k, v in metrics.items()},
            indent=2,
        )
    )

    print(f"\nSaved model   -> {settings.model_path}")
    print(f"Saved metrics -> {settings.metrics_path}")
    print("Saved zone_hour_stats and model_metadata to PostgreSQL")


if __name__ == "__main__":
    main()
