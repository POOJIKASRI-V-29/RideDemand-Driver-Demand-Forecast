"""Invalid parameters must be rejected clearly, not silently coerced."""
import pytest


@pytest.mark.parametrize(
    "query",
    [
        "day=Funday&hour=19&window=60",  # not a weekday
        "day=9&hour=19&window=60",  # weekday index out of range
        "day=Friday&hour=24&window=60",  # hour out of range
        "day=Friday&hour=-1&window=60",  # negative hour
        "day=Friday&hour=abc&window=60",  # hour not a number
        "day=Friday&hour=19&window=45",  # unsupported forecast window
        "day=Friday&hour=19&window=0",
    ],
)
@pytest.mark.parametrize(
    "endpoint", ["/api/demand", "/api/hotspots", "/api/recommendation", "/api/copilot"]
)
def test_invalid_parameters_are_rejected(client, endpoint, query):
    response = client.get(f"{endpoint}?{query}")
    assert response.status_code == 422
    assert "detail" in response.json()


def test_bad_day_message_lists_the_valid_options(client):
    detail = client.get("/api/demand?day=Funday").json()["detail"]
    assert "Funday" in detail
    assert "Monday" in detail


@pytest.mark.parametrize("limit", [0, -3, 101])
def test_out_of_range_hotspot_limit_is_rejected(client, limit):
    assert client.get(f"/api/hotspots?limit={limit}").status_code == 422


def test_copilot_post_rejects_an_unknown_day(client):
    response = client.post("/api/copilot", json={"day": "Caturday", "hour": 9, "window": 60})
    assert response.status_code == 422


def test_copilot_post_rejects_an_out_of_range_hour(client):
    response = client.post("/api/copilot", json={"day": "Friday", "hour": 40, "window": 60})
    assert response.status_code == 422


def test_service_reports_503_when_no_data_is_loaded(client, db_session):
    """An unpopulated database is a server-state problem, not a client error."""
    from sqlalchemy import text

    db_session.execute(text("TRUNCATE zones RESTART IDENTITY CASCADE"))
    db_session.commit()

    response = client.get("/api/demand?day=Friday&hour=19&window=60")
    assert response.status_code == 503
    assert "prepare_data" in response.json()["detail"]
