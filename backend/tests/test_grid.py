"""The grid definition must be identical everywhere it is applied."""
import pytest

from app.ml.grid import cell_bounds, cell_center, cell_of, snap
from app.ml.places import label_cell, nearest_neighbourhood
from app.services.demand_service import parse_day


@pytest.mark.parametrize(
    ("lat", "lng", "expected"),
    [
        (40.7580, -73.9855, (40.75, -73.99)),
        (40.7500, -73.9900, (40.75, -73.99)),  # exactly on a corner
        (40.7599, -73.9801, (40.75, -73.99)),  # just inside the same cell
        (40.7601, -73.9799, (40.76, -73.98)),  # the next cell over
    ],
)
def test_cells_are_the_floor_of_the_coordinate(lat, lng, expected):
    assert cell_of(lat, lng, 0.01) == expected


def test_negative_longitudes_floor_downwards():
    """floor(-73.9855 / 0.01) * 0.01 is -73.99, not -73.98."""
    assert snap(-73.9855, 0.01) == -73.99


def test_the_grid_size_is_configurable():
    assert cell_of(40.7580, -73.9855, 0.05) == (40.75, -74.0)
    assert cell_of(40.7580, -73.9855, 0.001) == (40.758, -73.986)


def test_centre_and_bounds_are_consistent():
    cell = cell_of(40.7580, -73.9855, 0.01)
    (south, west), (north, east) = cell_bounds(*cell, 0.01)
    centre = cell_center(*cell, 0.01)

    assert south < centre[0] < north
    assert west < centre[1] < east
    assert centre == (round((south + north) / 2, 6), round((west + east) / 2, 6))


def test_a_cell_containing_a_reference_point_keeps_the_plain_name():
    lat, lng = 40.7580, -73.9855  # Times Square
    centre = cell_center(*cell_of(lat, lng, 0.01), 0.01)
    assert label_cell(centre[0], centre[1], 0.01) == "Times Square"


def test_neighbouring_cells_get_distinct_compass_labels():
    name, c_lat, c_lng = nearest_neighbourhood(40.7580, -73.9855)
    assert name == "Times Square"
    far_north = label_cell(c_lat + 0.05, c_lng, 0.01)
    far_south = label_cell(c_lat - 0.05, c_lng, 0.01)
    assert far_north != far_south


@pytest.mark.parametrize(
    ("value", "expected"),
    [("Monday", 0), ("monday", 0), ("mon", 0), ("Sunday", 6), (3, 3), ("6", 6)],
)
def test_parse_day_accepts_names_and_indexes(value, expected):
    assert parse_day(value) == expected


@pytest.mark.parametrize("value", ["Funday", "", "7", "-1", "sundae"])
def test_parse_day_rejects_anything_else(value):
    with pytest.raises(ValueError):
        parse_day(value)
