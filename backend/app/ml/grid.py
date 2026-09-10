"""The geographic grid.

One definition, used by preprocessing, training, the API and (via the API
payload) the frontend. A cell is identified by the coordinates of its
south-west corner:

    grid_lat = floor(latitude  / grid_size) * grid_size
    grid_lng = floor(longitude / grid_size) * grid_size

``grid_size`` is configurable (``GRID_SIZE`` env var, default 0.01 degrees).
Values are rounded to 6 decimals so that floating point noise never produces
two "different" cells for the same location.
"""
from __future__ import annotations

import math

ROUNDING = 6


def snap(value: float, grid_size: float) -> float:
    """Snap a single coordinate to the south-west edge of its cell."""
    return round(math.floor(value / grid_size) * grid_size, ROUNDING)


def cell_of(lat: float, lng: float, grid_size: float) -> tuple[float, float]:
    """Return the (grid_lat, grid_lng) cell containing a point."""
    return snap(lat, grid_size), snap(lng, grid_size)


def cell_center(grid_lat: float, grid_lng: float, grid_size: float) -> tuple[float, float]:
    """Centroid of a cell — the point the map marker is drawn at."""
    return (
        round(grid_lat + grid_size / 2, ROUNDING),
        round(grid_lng + grid_size / 2, ROUNDING),
    )


def cell_bounds(
    grid_lat: float, grid_lng: float, grid_size: float
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Leaflet-style ((south, west), (north, east)) bounds for a cell."""
    return (
        (round(grid_lat, ROUNDING), round(grid_lng, ROUNDING)),
        (round(grid_lat + grid_size, ROUNDING), round(grid_lng + grid_size, ROUNDING)),
    )
