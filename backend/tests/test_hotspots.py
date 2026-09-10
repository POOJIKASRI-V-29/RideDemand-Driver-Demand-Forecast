"""Hotspot ranking is the backend's job, and must agree with /api/demand."""


def test_hotspots_are_ranked_by_predicted_demand(client):
    body = client.get("/api/hotspots?day=Friday&hour=19&window=60").json()
    hotspots = body["hotspots"]

    assert [h["name"] for h in hotspots] == ["Midtown", "SoHo", "Harlem", "Astoria"]
    demands = [h["predicted_demand"] for h in hotspots]
    assert demands == sorted(demands, reverse=True)


def test_limit_returns_the_busiest_n(client):
    hotspots = client.get("/api/hotspots?day=Friday&hour=19&window=60&limit=2").json()[
        "hotspots"
    ]
    assert len(hotspots) == 2
    assert [h["name"] for h in hotspots] == ["Midtown", "SoHo"]


def test_hotspots_match_the_demand_endpoint_exactly(client):
    query = "day=Saturday&hour=8&window=120"
    demand = client.get(f"/api/demand?{query}").json()["zones"]
    hotspots = client.get(f"/api/hotspots?{query}&limit=4").json()["hotspots"]

    assert [z["zone_id"] for z in demand] == [h["zone_id"] for h in hotspots]
    assert [z["predicted_demand"] for z in demand] == [
        h["predicted_demand"] for h in hotspots
    ]


def test_ranking_changes_with_the_forecast_window(client):
    """SoHo is busier than Midtown at 20:00, which a 2-hour window must reflect."""
    one_hour = client.get("/api/hotspots?day=Friday&hour=20&window=60").json()["hotspots"]
    assert one_hour[0]["name"] == "SoHo"
