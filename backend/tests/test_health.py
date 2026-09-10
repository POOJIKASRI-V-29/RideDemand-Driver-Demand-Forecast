"""The health endpoint should describe what the service can actually do."""


def test_health_reports_loaded_data(client):
    response = client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["zones_loaded"] == 4
    assert body["observations_loaded"] == 4
    # No model file is loaded in this fixture, so it must say so rather than lie.
    assert body["model_loaded"] is False
    assert isinstance(body["llm_copilot"], bool)


def test_config_exposes_grid_and_selectors(client):
    body = client.get("/api/config").json()
    assert body["grid_size"] == 0.01
    assert body["days"][0] == "Monday"
    assert len(body["hours"]) == 24
    assert [w["value"] for w in body["windows"]] == [30, 60, 120]


def test_model_endpoint_falls_back_to_baseline_without_a_model(client):
    body = client.get("/api/model").json()
    assert body["source"] == "historical_baseline"
    # The baseline has no measured MAE, so none may be reported.
    assert body["mae"] is None
    assert "historical" in body["note"].lower()


def test_model_endpoint_reports_measured_metrics_when_a_model_is_loaded(client_with_metadata):
    body = client_with_metadata.get("/api/model").json()
    assert body["source"] == "gradient_boosting_model"
    assert body["mae"] == 1.5
    assert body["baseline_mae"] == 1.6
    assert body["dataset_name"] == "test fixture"
