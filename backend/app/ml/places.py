"""Approximate neighbourhood labels for grid cells.

A grid cell is a bare pair of coordinates, which is useless to a driver, so
each cell is labelled with the nearest entry from the bundled table of
neighbourhood centroids below. When several cells map to the same
neighbourhood, a compass suffix derived from the cell's offset relative to that
centroid keeps the labels distinct (e.g. "Midtown", "Midtown NE").

These labels are approximate and are NOT authoritative neighbourhood
boundaries: the centroids are hand-entered reference points, and nearest-point
assignment ignores real borough and neighbourhood geometry. They exist purely
so the UI can say "Midtown" instead of "40.75, -73.98".
"""
from __future__ import annotations

import math

# name -> (latitude, longitude)
NEIGHBOURHOOD_CENTROIDS: dict[str, tuple[float, float]] = {
    # Manhattan
    "Financial District": (40.7075, -74.0113),
    "Battery Park City": (40.7115, -74.0161),
    "Tribeca": (40.7163, -74.0086),
    "Chinatown": (40.7158, -73.9970),
    "Lower East Side": (40.7150, -73.9843),
    "SoHo": (40.7233, -74.0030),
    "Greenwich Village": (40.7336, -74.0027),
    "East Village": (40.7265, -73.9815),
    "West Village": (40.7358, -74.0036),
    "Chelsea": (40.7465, -74.0014),
    "Flatiron": (40.7401, -73.9903),
    "Gramercy": (40.7368, -73.9845),
    "Kips Bay": (40.7424, -73.9800),
    "Murray Hill": (40.7479, -73.9757),
    "Times Square": (40.7580, -73.9855),
    "Midtown East": (40.7549, -73.9707),
    "Turtle Bay": (40.7527, -73.9680),
    "Hell's Kitchen": (40.7638, -73.9918),
    "Columbus Circle": (40.7681, -73.9819),
    "Lincoln Square": (40.7736, -73.9847),
    "Upper East Side": (40.7736, -73.9566),
    "Lenox Hill": (40.7662, -73.9626),
    "Yorkville": (40.7760, -73.9490),
    "Upper West Side": (40.7870, -73.9754),
    "Central Park": (40.7812, -73.9665),
    "Morningside Heights": (40.8090, -73.9625),
    "Harlem": (40.8116, -73.9465),
    "East Harlem": (40.7957, -73.9389),
    "Washington Heights": (40.8417, -73.9394),
    "Inwood": (40.8677, -73.9212),
    # Brooklyn
    "Greenpoint": (40.7304, -73.9540),
    "Williamsburg": (40.7081, -73.9571),
    "Bushwick": (40.6944, -73.9213),
    "Bedford-Stuyvesant": (40.6872, -73.9418),
    "DUMBO": (40.7033, -73.9881),
    "Brooklyn Heights": (40.6960, -73.9954),
    "Downtown Brooklyn": (40.6928, -73.9857),
    "Fort Greene": (40.6892, -73.9740),
    "Prospect Heights": (40.6774, -73.9668),
    "Crown Heights": (40.6694, -73.9422),
    "Park Slope": (40.6710, -73.9814),
    "Gowanus": (40.6736, -73.9950),
    "Carroll Gardens": (40.6795, -73.9990),
    "Red Hook": (40.6772, -74.0087),
    "Sunset Park": (40.6455, -74.0121),
    "Bay Ridge": (40.6264, -74.0299),
    "Flatbush": (40.6409, -73.9624),
    "Coney Island": (40.5755, -73.9707),
    "Brighton Beach": (40.5780, -73.9597),
    # Queens
    "Long Island City": (40.7447, -73.9485),
    "Astoria": (40.7644, -73.9235),
    "Sunnyside": (40.7433, -73.9196),
    "Woodside": (40.7454, -73.9060),
    "Jackson Heights": (40.7557, -73.8831),
    "Elmhurst": (40.7362, -73.8770),
    "Corona": (40.7449, -73.8626),
    "Flushing": (40.7674, -73.8331),
    "Forest Hills": (40.7196, -73.8448),
    "Rego Park": (40.7257, -73.8618),
    "Ridgewood": (40.7043, -73.9018),
    "Jamaica": (40.7020, -73.7889),
    "JFK Airport": (40.6413, -73.7781),
    "LaGuardia Airport": (40.7769, -73.8740),
    # Bronx
    "Mott Haven": (40.8090, -73.9229),
    "Hunts Point": (40.8126, -73.8840),
    "Fordham": (40.8610, -73.8900),
    "Riverdale": (40.8900, -73.9125),
    "Pelham Bay": (40.8500, -73.8330),
    # Staten Island
    "St. George": (40.6437, -74.0736),
    # New Jersey waterfront (inside the study bounding box)
    "Hoboken": (40.7440, -74.0324),
    "Jersey City": (40.7178, -74.0431),
}

_OCTANTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def _squared_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Planar squared distance with a cos(lat) correction on longitude.

    Good enough for nearest-label assignment over a single city; it is not used
    for any figure shown to the user.
    """
    lat_scale = math.cos(math.radians((a[0] + b[0]) / 2))
    dlat = a[0] - b[0]
    dlng = (a[1] - b[1]) * lat_scale
    return dlat * dlat + dlng * dlng


def nearest_neighbourhood(lat: float, lng: float) -> tuple[str, float, float]:
    """Return (name, centroid_lat, centroid_lng) of the closest reference point."""
    best_name = ""
    best_point = (0.0, 0.0)
    best_dist = float("inf")
    for name, point in NEIGHBOURHOOD_CENTROIDS.items():
        dist = _squared_distance((lat, lng), point)
        if dist < best_dist:
            best_dist, best_name, best_point = dist, name, point
    return best_name, best_point[0], best_point[1]


def _octant(dlat: float, dlng: float) -> str:
    angle = math.degrees(math.atan2(dlng, dlat)) % 360.0
    return _OCTANTS[int((angle + 22.5) % 360.0 // 45.0)]


def label_cell(center_lat: float, center_lng: float, grid_size: float) -> str:
    """Label a cell by its nearest neighbourhood, plus a compass suffix.

    The suffix is omitted when the neighbourhood centroid falls inside the cell
    itself, so the busiest cell of an area keeps the clean name.
    """
    name, c_lat, c_lng = nearest_neighbourhood(center_lat, center_lng)
    half = grid_size / 2
    if abs(center_lat - c_lat) <= half and abs(center_lng - c_lng) <= half:
        return name
    return f"{name} {_octant(center_lat - c_lat, center_lng - c_lng)}"
