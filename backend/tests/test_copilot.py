"""The copilot must stay grounded in the prediction, and must never be required."""
from app.services import copilot_service


def test_fallback_is_used_when_no_llm_is_configured(client, monkeypatch):
    monkeypatch.setattr(copilot_service, "llm_available", lambda: False)

    body = client.post(
        "/api/copilot", json={"day": "Friday", "hour": 19, "window": 60}
    ).json()

    assert body["source"] == "fallback"
    assert body["model"] is None
    assert body["message"]


def test_fallback_text_only_states_predicted_figures(client, monkeypatch):
    monkeypatch.setattr(copilot_service, "llm_available", lambda: False)

    body = client.post(
        "/api/copilot", json={"day": "Friday", "hour": 19, "window": 60}
    ).json()
    message = body["message"]

    assert "Midtown" in message
    assert "100.0" in message  # the predicted figure, unmodified
    assert body["grounded_on"]["top_area"] == "Midtown"
    assert body["grounded_on"]["top_area_predicted_requests"] == 100.0
    # Nothing the dataset cannot support may appear.
    for forbidden in ("km", "minutes away", "ETA", "confidence", "₹", "$"):
        assert forbidden not in message


def test_grounding_matches_the_recommendation_endpoint(client, monkeypatch):
    monkeypatch.setattr(copilot_service, "llm_available", lambda: False)

    recommendation = client.get(
        "/api/recommendation?day=Friday&hour=19&window=60"
    ).json()
    copilot = client.post(
        "/api/copilot", json={"day": "Friday", "hour": 19, "window": 60}
    ).json()

    assert copilot["grounded_on"]["top_area"] == recommendation["zone"]["name"]
    assert (
        copilot["grounded_on"]["top_area_predicted_requests"]
        == recommendation["zone"]["predicted_demand"]
    )


def test_llm_output_is_used_when_the_api_call_succeeds(client, monkeypatch):
    """The LLM branch, exercised without touching the network."""
    monkeypatch.setattr(copilot_service, "llm_available", lambda: True)
    monkeypatch.setattr(
        copilot_service,
        "_llm_message",
        lambda grounded: (f"Head for {grounded['top_area']}.", "claude-opus-5"),
    )

    body = client.post(
        "/api/copilot", json={"day": "Friday", "hour": 19, "window": 60}
    ).json()

    assert body["source"] == "llm"
    assert body["model"] == "claude-opus-5"
    assert body["message"] == "Head for Midtown."


def test_an_llm_failure_falls_back_instead_of_erroring(client, monkeypatch):
    monkeypatch.setattr(copilot_service, "llm_available", lambda: True)
    monkeypatch.setattr(copilot_service, "_llm_message", lambda grounded: None)

    response = client.post(
        "/api/copilot", json={"day": "Friday", "hour": 19, "window": 60}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "fallback"
    assert "Midtown" in body["message"]


def test_get_and_post_agree(client, monkeypatch):
    monkeypatch.setattr(copilot_service, "llm_available", lambda: False)

    from_get = client.get("/api/copilot?day=Friday&hour=19&window=60").json()
    from_post = client.post(
        "/api/copilot", json={"day": "Friday", "hour": 19, "window": 60}
    ).json()

    assert from_get["message"] == from_post["message"]
