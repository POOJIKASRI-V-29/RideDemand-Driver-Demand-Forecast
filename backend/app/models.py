"""Database schema.

Four small tables, all populated by the scripts in ``backend/scripts``:

zones                 one row per occupied geographic grid cell
demand_observations   historical pickup counts per (zone, date, hour)
zone_hour_stats       aggregated historical demand per (zone, weekday, hour);
                      used both as a model feature and as the fallback baseline
model_metadata        one row per trained model, including its measured metrics
"""
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Zone(Base):
    """A single cell of the geographic grid.

    ``grid_lat``/``grid_lng`` are the south-west corner of the cell, computed as
    ``floor(coord / grid_size) * grid_size``.
    """

    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grid_lat: Mapped[float] = mapped_column(Float, nullable=False)
    grid_lng: Mapped[float] = mapped_column(Float, nullable=False)
    grid_size: Mapped[float] = mapped_column(Float, nullable=False)
    center_lat: Mapped[float] = mapped_column(Float, nullable=False)
    center_lng: Mapped[float] = mapped_column(Float, nullable=False)
    # Approximate human-readable label (nearest bundled neighbourhood centroid).
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    total_pickups: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    observations: Mapped[list["DemandObservation"]] = relationship(
        back_populates="zone", cascade="all, delete-orphan"
    )
    hour_stats: Mapped[list["ZoneHourStat"]] = relationship(
        back_populates="zone", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("grid_lat", "grid_lng", "grid_size", name="uq_zone_cell"),
    )


class DemandObservation(Base):
    """Observed pickup count for one zone in one calendar hour."""

    __tablename__ = "demand_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zone_id: Mapped[int] = mapped_column(
        ForeignKey("zones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    obs_date: Mapped[date] = mapped_column(Date, nullable=False)
    hour: Mapped[int] = mapped_column(Integer, nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Mon
    is_weekend: Mapped[int] = mapped_column(Integer, nullable=False)
    ride_count: Mapped[int] = mapped_column(Integer, nullable=False)

    zone: Mapped[Zone] = relationship(back_populates="observations")

    __table_args__ = (
        UniqueConstraint("zone_id", "obs_date", "hour", name="uq_observation_slot"),
        Index("ix_obs_dow_hour", "day_of_week", "hour"),
    )


class ZoneHourStat(Base):
    """Historical demand aggregates for a (zone, day-of-week, hour) slot.

    These are computed from the TRAINING date range only (see
    ``scripts/train_model.py``) and serve two purposes: they are model features,
    and ``mean_demand`` is the baseline the model predicts a correction to.
    """

    __tablename__ = "zone_hour_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zone_id: Mapped[int] = mapped_column(
        ForeignKey("zones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    hour: Mapped[int] = mapped_column(Integer, nullable=False)

    # Mean and median demand for this exact slot.
    mean_demand: Mapped[float] = mapped_column(Float, nullable=False)
    median_demand: Mapped[float] = mapped_column(Float, nullable=False)
    max_demand: Mapped[float] = mapped_column(Float, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # Coarser pooled aggregates, which are less noisy than a slot with only a
    # handful of samples behind it.
    hourofday_mean: Mapped[float] = mapped_column(Float, nullable=False)
    dow_mean: Mapped[float] = mapped_column(Float, nullable=False)
    zone_mean_demand: Mapped[float] = mapped_column(Float, nullable=False)
    # Mean for (zone, hour) over the final stretch of the training period, which
    # tracks the level of demand more closely than the full-period mean.
    recent_hour_mean: Mapped[float] = mapped_column(Float, nullable=False)

    zone: Mapped[Zone] = relationship(back_populates="hour_stats")

    __table_args__ = (
        UniqueConstraint("zone_id", "day_of_week", "hour", name="uq_zone_slot"),
        Index("ix_stats_dow_hour", "day_of_week", "hour"),
    )


class ModelMetadata(Base):
    """Provenance and measured performance of a trained model.

    Every number stored here is produced by ``scripts/train_model.py`` on a
    held-out test split. Nothing in this table is hand-written.
    """

    __tablename__ = "model_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    algorithm: Mapped[str] = mapped_column(String(120), nullable=False)
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    features: Mapped[str] = mapped_column(String(500), nullable=False)
    n_train_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    n_test_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    n_zones: Mapped[int] = mapped_column(Integer, nullable=False)
    mae: Mapped[float] = mapped_column(Float, nullable=False)
    rmse: Mapped[float] = mapped_column(Float, nullable=False)
    r2: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_mae: Mapped[float] = mapped_column(Float, nullable=False)
    train_start: Mapped[date] = mapped_column(Date, nullable=False)
    train_end: Mapped[date] = mapped_column(Date, nullable=False)
    test_start: Mapped[date] = mapped_column(Date, nullable=False)
    test_end: Mapped[date] = mapped_column(Date, nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    grid_size: Mapped[float] = mapped_column(Float, nullable=False)
