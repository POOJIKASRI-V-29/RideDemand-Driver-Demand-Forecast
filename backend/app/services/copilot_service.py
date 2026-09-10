"""Driver Copilot — a short plain-language brief over the model's own numbers.

Two paths, one contract:

* **LLM** — when an Anthropic API key is configured, Claude is given the exact
  figures the prediction pipeline produced and asked to phrase them for a
  driver. The system prompt forbids inventing numbers; the model receives the
  values rather than being asked to estimate any.
* **Deterministic fallback** — when no key is configured, or the API call fails
  for any reason, the same figures are rendered through a template. The app
  keeps working, and the response says which path produced the text
  (``source: "llm" | "fallback"``).

Either way the numbers come from ``demand_service``, never from the model.
"""
from __future__ import annotations

import logging
import os

from sqlalchemy.orm import Session

from app.config import settings
from app.schemas import CopilotResponse, ForecastWindow, ZoneDemand
from app.services import demand_service

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Driver Copilot inside RideDemand, a ride-demand \
forecasting tool for taxi and ride-hailing drivers.

You will be given demand figures that a machine learning model has already \
predicted. Your only job is to explain them to a driver in plain, practical \
language.

Rules:
- Use ONLY the numbers given to you. Never invent, estimate, round differently, \
or extrapolate a figure.
- Never mention distance, travel time, earnings, fares or an ETA. That data \
does not exist here.
- Never state a confidence or accuracy percentage.
- Speak to the driver directly and practically. Two or three short sentences, \
about 45 words, no lists, no headings, no emoji.
- Predictions come from historical patterns, not live conditions, so avoid \
words like "right now" or "currently".
"""


def _has_api_key() -> bool:
    return bool(settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"))


def llm_available() -> bool:
    """True when an LLM copilot could be attempted."""
    if not _has_api_key():
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _hour_label(hour: int) -> str:
    """Match the 12-hour clock the dashboard's time selector shows."""
    suffix = "PM" if hour >= 12 else "AM"
    return f"{hour % 12 or 12}:00 {suffix}"


def _grounding(
    top: ZoneDemand, runner_up: ZoneDemand | None, window: ForecastWindow, day: str, hour: int
) -> dict[str, float | str]:
    """The exact figures the copilot is allowed to talk about."""
    grounded: dict[str, float | str] = {
        "day": day,
        "hour_label": _hour_label(hour),
        "forecast_window": demand_service.WINDOW_LABELS[int(window.value)],
        "top_area": top.name,
        "top_area_predicted_requests": top.predicted_demand,
        "top_area_predicted_requests_per_hour": top.predicted_per_hour,
        "top_area_demand_level": top.level.replace("_", " "),
    }
    if runner_up is not None:
        grounded["second_area"] = runner_up.name
        grounded["second_area_predicted_requests"] = runner_up.predicted_demand
        grounded["difference_vs_second_area"] = round(
            top.predicted_demand - runner_up.predicted_demand, 2
        )
    return grounded


def _fallback_message(grounded: dict[str, float | str]) -> str:
    """Deterministic template used whenever the LLM path is unavailable."""
    window = str(grounded["forecast_window"]).lower()
    top = float(grounded["top_area_predicted_requests"])
    parts = [
        f"Demand looks strongest around {grounded['top_area']} for {grounded['day']} "
        f"at {grounded['hour_label']}, with about {top:.1f} predicted requests "
        f"over the {window}."
    ]
    if "second_area" in grounded:
        lead = float(grounded["difference_vs_second_area"])
        parts.append(
            f"That is roughly {lead:.1f} more than {grounded['second_area']}, "
            "the next busiest area."
        )
    parts.append(
        "Positioning near there may improve your chances of picking up a request, "
        "though this is a historical pattern rather than live demand."
    )
    return " ".join(parts)


def _llm_message(grounded: dict[str, float | str]) -> tuple[str, str] | None:
    """Ask Claude to phrase the figures. Returns (text, model) or None on failure."""
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed; using the deterministic copilot.")
        return None

    facts = "\n".join(f"- {key}: {value}" for key, value in grounded.items())
    prompt = (
        "Here are the predicted demand figures for the driver's selected day, time and "
        f"forecast window:\n\n{facts}\n\n"
        "Write the driver's briefing using only these figures."
    )

    try:
        client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key or None,
            timeout=settings.copilot_timeout_seconds,
            max_retries=1,
        )
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=4000,
            output_config={"effort": "low"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        if response.stop_reason == "refusal":
            logger.warning("Copilot request was declined by the model; using the fallback.")
            return None
        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        ).strip()
        if not text:
            return None
        return text, response.model
    except anthropic.APIStatusError as exc:
        logger.warning("Copilot LLM call failed (%s); using the fallback.", exc.status_code)
    except anthropic.APIConnectionError:
        logger.warning("Copilot LLM call could not reach the API; using the fallback.")
    except Exception:  # pragma: no cover - defensive: the app must not fall over
        logger.exception("Unexpected copilot failure; using the fallback.")
    return None


def generate(
    db: Session, day_of_week: int, hour: int, window: ForecastWindow
) -> CopilotResponse:
    ranked = demand_service.predict_zones(db, day_of_week, hour, window)
    if not ranked:
        raise demand_service.NoDataError("No prediction available to brief the driver on.")

    info = demand_service.request_info(day_of_week, hour, window)
    grounded = _grounding(
        ranked[0], ranked[1] if len(ranked) > 1 else None, window, info.day, hour
    )

    if llm_available():
        result = _llm_message(grounded)
        if result is not None:
            message, model = result
            return CopilotResponse(
                request=info,
                generated_at=demand_service.now(),
                message=message,
                source="llm",
                model=model,
                grounded_on=grounded,
            )

    return CopilotResponse(
        request=info,
        generated_at=demand_service.now(),
        message=_fallback_message(grounded),
        source="fallback",
        model=None,
        grounded_on=grounded,
    )
