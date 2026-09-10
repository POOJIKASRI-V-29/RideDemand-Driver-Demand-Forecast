"""Historical-demand aggregates: how they are derived and how they are reused.

The trainer computes these from the training dates only and stores them in
``zone_hour_stats``; the API reads them straight back out of that table. Both
paths therefore see exactly the same numbers.
"""
from __future__ import annotations

import pandas as pd

RECENT_WINDOW_DAYS = 14

# zone_hour_stats column -> feature column consumed by the model
STAT_TO_FEATURE: dict[str, str] = {
    "mean_demand": "zone_hour_mean",
    "median_demand": "zone_hour_median",
    "hourofday_mean": "zone_hourofday_mean",
    "dow_mean": "zone_dow_mean",
    "zone_mean_demand": "zone_mean",
    "recent_hour_mean": "zone_recent_hour_mean",
}

STAT_COLUMNS: list[str] = [
    "zone_id",
    "day_of_week",
    "hour",
    "mean_demand",
    "median_demand",
    "max_demand",
    "sample_count",
    "hourofday_mean",
    "dow_mean",
    "zone_mean_demand",
    "recent_hour_mean",
]


def compute_stats(train: pd.DataFrame, recent_window_days: int = RECENT_WINDOW_DAYS) -> pd.DataFrame:
    """Build the full ``zone_hour_stats`` table from a training panel.

    ``train`` must have columns zone_id, obs_date, hour, day_of_week, ride_count.
    """
    slot = (
        train.groupby(["zone_id", "day_of_week", "hour"])["ride_count"]
        .agg(mean_demand="mean", median_demand="median", max_demand="max", sample_count="size")
        .reset_index()
    )
    hourofday = (
        train.groupby(["zone_id", "hour"])["ride_count"]
        .mean()
        .reset_index(name="hourofday_mean")
    )
    dow = (
        train.groupby(["zone_id", "day_of_week"])["ride_count"]
        .mean()
        .reset_index(name="dow_mean")
    )
    zone = train.groupby("zone_id")["ride_count"].mean().reset_index(name="zone_mean_demand")

    cutoff = train["obs_date"].max() - pd.Timedelta(days=recent_window_days)
    recent = (
        train[train["obs_date"] > cutoff]
        .groupby(["zone_id", "hour"])["ride_count"]
        .mean()
        .reset_index(name="recent_hour_mean")
    )

    stats = (
        slot.merge(hourofday, on=["zone_id", "hour"], how="left")
        .merge(dow, on=["zone_id", "day_of_week"], how="left")
        .merge(zone, on="zone_id", how="left")
        .merge(recent, on=["zone_id", "hour"], how="left")
    )
    stats["zone_mean_demand"] = stats["zone_mean_demand"].fillna(0.0)
    for column in ("hourofday_mean", "dow_mean", "recent_hour_mean", "mean_demand", "median_demand"):
        stats[column] = stats[column].fillna(stats["zone_mean_demand"])
    stats["max_demand"] = stats["max_demand"].fillna(0.0)
    return stats[STAT_COLUMNS]


def stats_to_features(stats: pd.DataFrame) -> pd.DataFrame:
    """Rename ``zone_hour_stats`` columns into the model's feature names."""
    return stats.rename(columns=STAT_TO_FEATURE)


def attach_features(panel: pd.DataFrame, stats: pd.DataFrame) -> pd.DataFrame:
    """Join the aggregates onto a (zone, date, hour) panel."""
    features = stats_to_features(stats).drop(columns=["max_demand", "sample_count"])
    out = panel.merge(features, on=["zone_id", "day_of_week", "hour"], how="left")
    out["zone_mean"] = out["zone_mean"].fillna(0.0)
    for column in (
        "zone_hour_mean",
        "zone_hour_median",
        "zone_hourofday_mean",
        "zone_dow_mean",
        "zone_recent_hour_mean",
    ):
        out[column] = out[column].fillna(out["zone_mean"])
    return out
