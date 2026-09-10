"""The demand endpoint: predictions, window arithmetic and the hourly profile."""
import pytest


def test_demand_returns_every_zone_ranked(client):
    body = client.get("/api/demand?day=Friday&hour=19&window=60").json()

    assert body["request"]["day"] == "Friday"
    assert body["request"]["day_of_week"] == 4
    assert body["request"]["window_label"] == "Next 60 min"

    names = [zone["name"] for zone in body["zones"]]
    assert names == ["Midtown", "SoHo", "Harlem", "Astoria"]

    demands = [zone["predicted_demand"] for zone in body["zones"]]
    assert demands == sorted(demands, reverse=True)
    assert demands[0] == 100.0


def test_intensity_and_level_are_relative_to_the_busiest_zone(client):
    zones = client.get("/api/demand?day=Friday&hour=19&window=60").json()["zones"]
    by_name = {zone["name"]: zone for zone in zones}

    assert by_name["Midtown"]["intensity"] == 1.0
    assert by_name["Midtown"]["level"] == "very_high"
    assert by_name["SoHo"]["intensity"] == pytest.approx(0.6)
    assert by_name["SoHo"]["level"] == "high"
    assert by_name["Astoria"]["level"] == "low"


def test_grid_geometry_matches_the_configured_cell_size(client):
    zone = client.get("/api/demand?day=Friday&hour=19&window=60").json()["zones"][0]
    (south, west), (north, east) = zone["bounds"]

    assert zone["grid_size"] == 0.01
    assert (south, west) == (zone["grid_lat"], zone["grid_lng"])
    assert north == pytest.approx(south + 0.01)
    assert east == pytest.approx(west + 0.01)
    assert zone["center"]["lat"] == pytest.approx(south + 0.005)
    assert zone["center"]["lng"] == pytest.approx(west + 0.005)


def test_thirty_minute_window_is_half_the_hourly_rate(client):
    half = client.get("/api/demand?day=Friday&hour=19&window=30").json()["zones"][0]
    assert half["predicted_per_hour"] == 100.0
    assert half["predicted_demand"] == 50.0


def test_two_hour_window_sums_the_selected_and_following_hour(client):
    zones = client.get("/api/demand?day=Friday&hour=19&window=120").json()["zones"]
    by_name = {zone["name"]: zone for zone in zones}

    # Midtown: 100 at 19:00 plus 80 at 20:00. SoHo: 60 plus 90, which overtakes it.
    assert by_name["Midtown"]["predicted_demand"] == 180.0
    assert by_name["SoHo"]["predicted_demand"] == 150.0
    assert zones[0]["name"] == "Midtown"


def test_hourly_profile_covers_the_whole_day(client):
    body = client.get("/api/demand?day=Friday&hour=19&window=60").json()
    profile = body["hourly_profile"]

    assert [point["hour"] for point in profile] == list(range(24))
    # 100 + 60 + 20 + 5 across the four fixture zones at 19:00.
    assert profile[19]["total_demand"] == 185.0
    assert body["summary"]["peak_hour"] == 19
    assert body["summary"]["peak_zone_name"] == "Midtown"


def test_limit_trims_the_zone_list_without_changing_the_ranking(client):
    body = client.get("/api/demand?day=Friday&hour=19&window=60&limit=2").json()
    assert [zone["name"] for zone in body["zones"]] == ["Midtown", "SoHo"]
    # The summary still describes the full forecast.
    assert body["summary"]["zone_count"] == 4


def test_day_accepts_names_abbreviations_and_indexes(client):
    for value in ("Friday", "friday", "fri", "4"):
        body = client.get(f"/api/demand?day={value}&hour=19&window=60").json()
        assert body["request"]["day_of_week"] == 4


def test_a_quiet_slot_still_returns_a_usable_forecast(client):
    """Every fixture zone averages 1.0 at 03:00, so nothing should rank as busy."""
    body = client.get("/api/demand?day=Friday&hour=3&window=60").json()
    assert len(body["zones"]) == 4
    assert all(zone["predicted_demand"] == 1.0 for zone in body["zones"])
