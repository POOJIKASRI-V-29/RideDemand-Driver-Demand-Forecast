"""The recommendation must come from the same ranking the rest of the app sees."""


def test_recommendation_is_the_top_ranked_zone(client):
    query = "day=Friday&hour=19&window=60"
    top = client.get(f"/api/hotspots?{query}&limit=1").json()["hotspots"][0]
    recommendation = client.get(f"/api/recommendation?{query}").json()

    assert recommendation["rank"] == 1
    assert recommendation["zone"]["zone_id"] == top["zone_id"]
    assert recommendation["zone"]["predicted_demand"] == top["predicted_demand"]


def test_lead_and_share_are_computed_from_the_prediction(client):
    body = client.get("/api/recommendation?day=Friday&hour=19&window=60").json()

    # Midtown 100 vs SoHo 60; top-10 total is 100 + 60 + 20 + 5 = 185.
    assert body["lead_over_runner_up"] == 40.0
    assert body["runner_up_name"] == "SoHo"
    assert round(body["share_of_top_zones"], 4) == round(100 / 185, 4)


def test_reasons_never_claim_distance_travel_time_or_confidence(client):
    body = client.get("/api/recommendation?day=Friday&hour=19&window=60").json()
    labels = " ".join(reason["label"].lower() for reason in body["reasons"])

    assert "distance" not in labels
    assert "eta" not in labels
    assert "travel" not in labels
    assert "confidence" not in labels
    assert len(body["reasons"]) == 3


def test_recommendation_follows_the_window(client):
    """At 20:00 SoHo is the busiest zone, so it must be the recommendation."""
    body = client.get("/api/recommendation?day=Friday&hour=20&window=60").json()
    assert body["zone"]["name"] == "SoHo"
