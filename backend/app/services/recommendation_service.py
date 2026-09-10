"""Choosing where the driver should position themselves.

The choice is made here, on the backend, from the same ranked prediction the
map and the hotspot list are drawn from. The frontend only renders it.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.schemas import (
    ForecastWindow,
    RecommendationReason,
    RecommendationResponse,
    ZoneDemand,
)
from app.services import demand_service

TOP_N_FOR_SHARE = 10


def build_recommendation(
    ranked: list[ZoneDemand], day_of_week: int, hour: int, window: ForecastWindow
) -> tuple[ZoneDemand, list[RecommendationReason], float, float, str | None]:
    """Return the top zone plus the figures that justify it.

    Every reason is derived from the prediction itself — there is no distance,
    travel time or confidence score here, because none of those can be computed
    from this dataset.
    """
    best = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    lead = round(best.predicted_demand - runner_up.predicted_demand, 2) if runner_up else 0.0

    top_slice = ranked[:TOP_N_FOR_SHARE]
    top_total = sum(z.predicted_demand for z in top_slice)
    share = round(best.predicted_demand / top_total, 4) if top_total > 0 else 0.0

    window_label = demand_service.WINDOW_LABELS[int(window.value)]
    reasons = [
        RecommendationReason(
            label="Lead over next area",
            value=f"+{lead:g}",
            detail=(
                f"Predicted requests above {runner_up.name} over the {window_label.lower()}."
                if runner_up
                else "Only one zone was predicted for this slot."
            ),
        ),
        RecommendationReason(
            label=f"Share of top {len(top_slice)}",
            value=f"{share * 100:.0f}%",
            detail="Portion of the busiest zones' combined predicted demand in this one cell.",
        ),
        RecommendationReason(
            label="History behind it",
            value=f"{best.historical_samples} obs",
            detail=(
                f"Past observations of this cell at this weekday and hour, averaging "
                f"{best.historical_mean_per_hour:g} pickups/hour."
            ),
        ),
    ]
    return best, reasons, lead, share, runner_up.name if runner_up else None


def recommend(
    db: Session, day_of_week: int, hour: int, window: ForecastWindow
) -> RecommendationResponse:
    ranked = demand_service.predict_zones(db, day_of_week, hour, window)
    if not ranked:
        raise demand_service.NoDataError("No zones available to recommend from.")

    best, reasons, lead, share, runner_up_name = build_recommendation(
        ranked, day_of_week, hour, window
    )
    return RecommendationResponse(
        request=demand_service.request_info(day_of_week, hour, window),
        generated_at=demand_service.now(),
        model_info=demand_service.model_info(db),
        zone=best,
        rank=1,
        lead_over_runner_up=lead,
        runner_up_name=runner_up_name,
        share_of_top_zones=share,
        reasons=reasons,
    )
