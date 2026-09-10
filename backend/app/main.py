"""RideDemand API entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.api import copilot, demand, hotspots, meta, recommendation
from app.config import settings
from app.database import init_db
from app.services.demand_service import get_model

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ridedemand")

DESCRIPTION = """\
Predicted ride demand across a geographic grid, for drivers deciding where to
position themselves next.

Historical trip records are aggregated into a configurable latitude/longitude
grid, stored in PostgreSQL, and used to train a gradient boosting model whose
measured error is reported by `/api/model`. Every figure these endpoints return
is computed from that pipeline.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
    except SQLAlchemyError:
        logger.exception("Could not reach the database at startup; /health will report it.")

    if get_model() is None:
        logger.warning(
            "No trained model at %s — predictions fall back to the historical average "
            "baseline. Run scripts/train_model.py; the model is picked up automatically, "
            "without restarting this process.",
            settings.model_path,
        )
    else:
        logger.info("Loaded demand model from %s", settings.model_path)
    yield


app = FastAPI(
    title="RideDemand API",
    description=DESCRIPTION,
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(demand.router)
app.include_router(hotspots.router)
app.include_router(recommendation.router)
app.include_router(copilot.router)
