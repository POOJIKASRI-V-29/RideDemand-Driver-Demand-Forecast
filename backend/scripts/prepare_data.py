"""Download and preprocess the raw ride dataset into hourly grid demand.

Dataset
-------
FiveThirtyEight's ``uber-tlc-foil-response`` repository, which publishes the
raw Uber pickup records New York City's Taxi & Limousine Commission released
in response to a Freedom of Information Law request. Each row is one pickup:

    "Date/Time","Lat","Lon","Base"
    "4/1/2014 0:11:00",40.7690,-73.9549,"B02512"

Source: https://github.com/fivethirtyeight/uber-tlc-foil-response

Only the 2014 files carry raw latitude/longitude, which is what makes a
geographic grid possible — the later TLC releases publish anonymised zone IDs
instead.

Output
------
``data/processed/zones.csv``        one row per retained grid cell
``data/processed/observations.csv`` (zone cell, date, hour) -> pickup count,
                                    non-zero rows only

Raw CSVs land in ``data/raw`` and are git-ignored; nothing large is committed.

Usage
-----
    python -m scripts.prepare_data --months apr14 may14 jun14
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.ml.grid import ROUNDING, cell_center  # noqa: E402
from app.ml.places import label_cell  # noqa: E402

BASE_URL = (
    "https://raw.githubusercontent.com/fivethirtyeight/uber-tlc-foil-response"
    "/master/uber-trip-data/uber-raw-data-{month}.csv"
)
AVAILABLE_MONTHS = ["apr14", "may14", "jun14", "jul14", "aug14", "sep14"]
DATASET_NAME = "fivethirtyeight/uber-tlc-foil-response (NYC Uber pickups, 2014)"


def download_month(month: str, raw_dir: Path) -> Path:
    """Fetch one monthly CSV, reusing the local copy when present."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / f"uber-raw-data-{month}.csv"
    if target.exists() and target.stat().st_size > 0:
        print(f"  [cached] {target.name} ({target.stat().st_size / 1e6:.1f} MB)")
        return target

    url = BASE_URL.format(month=month)
    print(f"  [download] {url}")
    tmp = target.with_suffix(".part")
    try:
        urllib.request.urlretrieve(url, tmp)
    except Exception as exc:  # pragma: no cover - network failure path
        tmp.unlink(missing_ok=True)
        raise SystemExit(
            f"Failed to download {url}: {exc}\n"
            "This step needs internet access. Download the CSV manually into "
            f"{raw_dir} and re-run."
        ) from exc
    tmp.rename(target)
    print(f"  [saved]    {target.name} ({target.stat().st_size / 1e6:.1f} MB)")
    return target


def load_pickups(paths: list[Path], sample_fraction: float) -> pd.DataFrame:
    frames = []
    for path in paths:
        df = pd.read_csv(path, usecols=["Date/Time", "Lat", "Lon"])
        if sample_fraction < 1.0:
            df = df.sample(frac=sample_fraction, random_state=settings.random_state)
        frames.append(df)
        print(f"  [read]     {path.name}: {len(df):,} rows")
    pickups = pd.concat(frames, ignore_index=True)
    pickups["pickup_ts"] = pd.to_datetime(
        pickups["Date/Time"], format="%m/%d/%Y %H:%M:%S", errors="coerce"
    )
    pickups = pickups.dropna(subset=["pickup_ts", "Lat", "Lon"])
    return pickups.rename(columns={"Lat": "lat", "Lon": "lng"})[["pickup_ts", "lat", "lng"]]


def clip_to_bbox(pickups: pd.DataFrame) -> pd.DataFrame:
    before = len(pickups)
    mask = (
        pickups["lat"].between(settings.bbox_min_lat, settings.bbox_max_lat)
        & pickups["lng"].between(settings.bbox_min_lng, settings.bbox_max_lng)
    )
    out = pickups[mask]
    print(f"  [bbox]     kept {len(out):,} of {before:,} pickups inside the study area")
    return out


def assign_grid(pickups: pd.DataFrame, grid_size: float) -> pd.DataFrame:
    """Apply the shared grid definition: floor(coord / size) * size."""
    pickups = pickups.copy()
    pickups["grid_lat"] = np.round(
        np.floor(pickups["lat"] / grid_size) * grid_size, ROUNDING
    )
    pickups["grid_lng"] = np.round(
        np.floor(pickups["lng"] / grid_size) * grid_size, ROUNDING
    )
    return pickups


def aggregate_hourly(pickups: pd.DataFrame) -> pd.DataFrame:
    pickups = pickups.copy()
    pickups["obs_date"] = pickups["pickup_ts"].dt.date
    pickups["hour"] = pickups["pickup_ts"].dt.hour
    grouped = (
        pickups.groupby(["grid_lat", "grid_lng", "obs_date", "hour"], sort=False)
        .size()
        .reset_index(name="ride_count")
    )
    dates = pd.to_datetime(grouped["obs_date"])
    grouped["day_of_week"] = dates.dt.dayofweek  # Monday = 0
    grouped["is_weekend"] = (grouped["day_of_week"] >= 5).astype(int)
    return grouped


def build_zones(observations: pd.DataFrame, grid_size: float, min_pickups: int) -> pd.DataFrame:
    totals = (
        observations.groupby(["grid_lat", "grid_lng"], sort=False)["ride_count"]
        .sum()
        .reset_index(name="total_pickups")
    )
    kept = totals[totals["total_pickups"] >= min_pickups].copy()
    dropped = len(totals) - len(kept)
    share = kept["total_pickups"].sum() / max(totals["total_pickups"].sum(), 1)
    print(
        f"  [zones]    kept {len(kept):,} cells with >= {min_pickups} pickups "
        f"(dropped {dropped:,} sparse cells; retained {share:.1%} of all pickups)"
    )

    centers = [
        cell_center(row.grid_lat, row.grid_lng, grid_size)
        for row in kept.itertuples(index=False)
    ]
    kept["center_lat"] = [c[0] for c in centers]
    kept["center_lng"] = [c[1] for c in centers]
    kept["grid_size"] = grid_size
    kept["name"] = [
        label_cell(lat, lng, grid_size)
        for lat, lng in zip(kept["center_lat"], kept["center_lng"], strict=True)
    ]
    return kept.sort_values("total_pickups", ascending=False).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--months",
        nargs="+",
        default=["apr14", "may14", "jun14"],
        choices=AVAILABLE_MONTHS,
        help="Which monthly files to use (default: apr14 may14 jun14).",
    )
    parser.add_argument(
        "--grid-size",
        type=float,
        default=settings.grid_size,
        help=f"Grid cell edge in degrees (default {settings.grid_size}).",
    )
    parser.add_argument(
        "--min-cell-pickups",
        type=int,
        default=settings.min_cell_pickups,
        help="Drop grid cells with fewer total pickups than this.",
    )
    parser.add_argument(
        "--sample-fraction",
        type=float,
        default=1.0,
        help="Randomly subsample raw rows (useful for a quick smoke run).",
    )
    args = parser.parse_args()

    print(f"Dataset: {DATASET_NAME}")
    print(f"Grid size: {args.grid_size} degrees\n")

    print("1/5 Acquiring raw data")
    paths = [download_month(m, settings.raw_dir) for m in args.months]

    print("\n2/5 Loading pickups")
    pickups = load_pickups(paths, args.sample_fraction)
    print(f"  [total]    {len(pickups):,} pickups")

    print("\n3/5 Filtering to the study area")
    pickups = clip_to_bbox(pickups)

    print("\n4/5 Assigning grid cells and aggregating by hour")
    pickups = assign_grid(pickups, args.grid_size)
    observations = aggregate_hourly(pickups)
    print(f"  [hourly]   {len(observations):,} non-empty (cell, date, hour) slots")

    print("\n5/5 Selecting zones and writing output")
    zones = build_zones(observations, args.grid_size, args.min_cell_pickups)
    keys = set(zip(zones["grid_lat"], zones["grid_lng"], strict=True))
    observations = observations[
        [
            (lat, lng) in keys
            for lat, lng in zip(observations["grid_lat"], observations["grid_lng"], strict=True)
        ]
    ]

    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    zones_path = settings.processed_dir / "zones.csv"
    obs_path = settings.processed_dir / "observations.csv"
    zones.to_csv(zones_path, index=False)
    observations.sort_values(["obs_date", "hour"]).to_csv(obs_path, index=False)

    span = f"{observations['obs_date'].min()} .. {observations['obs_date'].max()}"
    print(f"\nWrote {zones_path} ({len(zones):,} zones)")
    print(f"Wrote {obs_path} ({len(observations):,} rows, {span})")
    print("\nNext: python -m scripts.load_db")


if __name__ == "__main__":
    main()
