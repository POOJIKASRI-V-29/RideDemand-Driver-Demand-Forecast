"""Test fixtures.

The suite runs against its own database so it never touches development data.
By default that is the configured ``DATABASE_URL`` with ``_test`` appended to
the database name, which means the tests follow the server the application is
already pointed at — locally or inside a container. Set ``TEST_DATABASE_URL``
to override. If no database can be reached the whole suite skips rather than
failing with connection noise.

The fixture seeds a small, hand-written demand fixture whose expected answers
are obvious by inspection, and forces the historical-average path so the
assertions stay exact. ``test_model.py`` covers the trained-model path
separately.
"""
from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import DemandObservation, ModelMetadata, Zone, ZoneHourStat
from app.services import demand_service

def _default_test_url() -> str:
    """The application database with ``_test`` appended to its name."""
    base, _, name = settings.database_url.rpartition("/")
    return f"{base}/{name}_test" if base else f"{settings.database_url}_test"


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or _default_test_url()

GRID_SIZE = 0.01

# (name, grid_lat, grid_lng, demand at Friday 19:00, demand at Friday 20:00)
FIXTURE_ZONES = [
    ("Midtown", 40.75, -73.99, 100.0, 80.0),
    ("SoHo", 40.72, -74.00, 60.0, 90.0),
    ("Harlem", 40.81, -73.95, 20.0, 10.0),
    ("Astoria", 40.76, -73.93, 5.0, 4.0),
]

FRIDAY = 4
HOUR = 19


def _ensure_database() -> bool:
    """Create the test database if it is missing. False when unreachable."""
    admin_url = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    target = TEST_DATABASE_URL.rsplit("/", 1)[1]
    try:
        engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{target}"'))
        engine.dispose()
        return True
    except SQLAlchemyError:
        return False


@pytest.fixture(scope="session")
def engine():
    if not _ensure_database():
        pytest.skip(f"No PostgreSQL server reachable at {TEST_DATABASE_URL}")
    engine = create_engine(TEST_DATABASE_URL, future=True)
    try:
        with engine.connect():
            pass
    except SQLAlchemyError:
        pytest.skip(f"Could not connect to {TEST_DATABASE_URL}")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


def _seed(session: Session) -> None:
    zones = []
    for name, lat, lng, _, _ in FIXTURE_ZONES:
        zones.append(
            Zone(
                grid_lat=lat,
                grid_lng=lng,
                grid_size=GRID_SIZE,
                center_lat=round(lat + GRID_SIZE / 2, 6),
                center_lng=round(lng + GRID_SIZE / 2, 6),
                name=name,
                total_pickups=1000,
            )
        )
    session.add_all(zones)
    session.flush()

    for zone, (_, _, _, this_hour, next_hour) in zip(zones, FIXTURE_ZONES, strict=True):
        for hour in range(24):
            if hour == HOUR:
                mean = this_hour
            elif hour == HOUR + 1:
                mean = next_hour
            else:
                mean = 1.0
            for day in range(7):
                value = mean if day == FRIDAY else 1.0
                session.add(
                    ZoneHourStat(
                        zone_id=zone.id,
                        day_of_week=day,
                        hour=hour,
                        mean_demand=value,
                        median_demand=value,
                        max_demand=value * 2,
                        sample_count=10,
                        hourofday_mean=value,
                        dow_mean=value,
                        zone_mean_demand=value,
                        recent_hour_mean=value,
                    )
                )
        session.add(
            DemandObservation(
                zone_id=zone.id,
                obs_date="2014-06-06",
                hour=HOUR,
                day_of_week=FRIDAY,
                is_weekend=0,
                ride_count=int(this_hour),
            )
        )

    session.add(
        ModelMetadata(
            algorithm="sklearn.ensemble.HistGradientBoostingRegressor",
            features="hour,day_of_week,is_weekend,grid_lat,grid_lng",
            n_train_rows=1000,
            n_test_rows=200,
            n_zones=len(FIXTURE_ZONES),
            mae=1.5,
            rmse=3.0,
            r2=0.9,
            baseline_mae=1.6,
            train_start="2014-04-01",
            train_end="2014-06-11",
            test_start="2014-06-12",
            test_end="2014-06-30",
            dataset_name="test fixture",
            grid_size=GRID_SIZE,
        )
    )
    session.commit()


@pytest.fixture
def db_session(engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, autoflush=False, future=True)
    with factory() as session:
        for table in ("zone_hour_stats", "demand_observations", "model_metadata", "zones"):
            session.execute(text(f"TRUNCATE {table} RESTART IDENTITY CASCADE"))
        session.commit()
        _seed(session)
        yield session


@pytest.fixture
def client(db_session: Session, monkeypatch) -> Iterator[TestClient]:
    """API client on the seeded database, forced onto the baseline predictor."""
    monkeypatch.setattr(demand_service, "get_model", lambda: None)
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def client_with_metadata(db_session: Session, monkeypatch) -> Iterator[TestClient]:
    """As ``client``, but pretending a trained model is loaded.

    Prediction still runs through the baseline, so the numbers stay exact; only
    the reported provenance changes.
    """

    class StubModel:
        metrics = {"target": "residual of ride_count against zone_hour_mean"}

        def predict(self, frame):
            return frame["zone_hour_mean"].to_numpy(dtype=float)

    monkeypatch.setattr(demand_service, "get_model", lambda: StubModel())
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
