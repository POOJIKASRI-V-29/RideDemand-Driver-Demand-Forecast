"""Load the processed CSVs produced by ``prepare_data.py`` into PostgreSQL.

Run after ``scripts.prepare_data``:

    python -m scripts.load_db

The load is idempotent: existing zones and observations are cleared first, so
re-running after a grid-size change leaves no stale rows behind.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.database import SessionLocal, engine, init_db  # noqa: E402
from app.models import Zone  # noqa: E402

COPY_BATCH = 50_000


def main() -> None:
    zones_path = settings.processed_dir / "zones.csv"
    obs_path = settings.processed_dir / "observations.csv"
    for path in (zones_path, obs_path):
        if not path.exists():
            raise SystemExit(f"Missing {path}. Run `python -m scripts.prepare_data` first.")

    print("1/4 Creating tables if needed")
    init_db()

    zones = pd.read_csv(zones_path)
    observations = pd.read_csv(obs_path)

    print("2/4 Clearing previous load")
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE zones RESTART IDENTITY CASCADE"))

    print(f"3/4 Inserting {len(zones):,} zones")
    with SessionLocal() as session:
        session.add_all(
            [
                Zone(
                    grid_lat=float(r.grid_lat),
                    grid_lng=float(r.grid_lng),
                    grid_size=float(r.grid_size),
                    center_lat=float(r.center_lat),
                    center_lng=float(r.center_lng),
                    name=str(r.name),
                    total_pickups=int(r.total_pickups),
                )
                for r in zones.itertuples(index=False)
            ]
        )
        session.commit()
        zone_ids = {
            (round(gl, 6), round(gn, 6)): zid
            for zid, gl, gn in session.execute(
                text("SELECT id, grid_lat, grid_lng FROM zones")
            ).all()
        }

    observations["zone_id"] = [
        zone_ids[(round(lat, 6), round(lng, 6))]
        for lat, lng in zip(
            observations["grid_lat"], observations["grid_lng"], strict=True
        )
    ]
    columns = ["zone_id", "obs_date", "hour", "day_of_week", "is_weekend", "ride_count"]
    frame = observations[columns]

    print(f"4/4 Copying {len(frame):,} demand observations")
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            statement = (
                f"COPY demand_observations ({', '.join(columns)}) FROM STDIN WITH (FORMAT CSV)"
            )
            with cur.copy(statement) as copy:
                for start in range(0, len(frame), COPY_BATCH):
                    chunk = frame.iloc[start : start + COPY_BATCH]
                    copy.write(chunk.to_csv(index=False, header=False))
        raw.commit()
    finally:
        raw.close()

    with engine.connect() as conn:
        n_zones = conn.execute(text("SELECT count(*) FROM zones")).scalar_one()
        n_obs = conn.execute(text("SELECT count(*) FROM demand_observations")).scalar_one()
        span = conn.execute(
            text("SELECT min(obs_date), max(obs_date) FROM demand_observations")
        ).one()

    print(f"\nLoaded {n_zones:,} zones and {n_obs:,} observations covering {span[0]} .. {span[1]}")
    print("Next: python -m scripts.train_model")


if __name__ == "__main__":
    main()
