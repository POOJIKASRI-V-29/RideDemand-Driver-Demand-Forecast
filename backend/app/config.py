"""Application configuration.

Every value can be overridden through environment variables (see .env.example).
The geographic grid size is deliberately configurable and is the single source
of truth used by preprocessing, training, the API and the frontend.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", BACKEND_DIR.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database -----------------------------------------------------------
    database_url: str = "postgresql+psycopg://ridedemand:ridedemand@localhost:5432/ridedemand"

    # --- Geographic grid ----------------------------------------------------
    # Cell edge length in decimal degrees. A cell is identified by its
    # south-west corner: floor(coord / grid_size) * grid_size.
    grid_size: float = 0.01

    # Bounding box of the study area (NYC, matching the Uber TLC dataset).
    city_name: str = "New York City"
    bbox_min_lat: float = 40.55
    bbox_max_lat: float = 40.92
    bbox_min_lng: float = -74.10
    bbox_max_lng: float = -73.70
    map_center_lat: float = 40.7420
    map_center_lng: float = -73.9800
    map_default_zoom: int = 12

    # --- Modelling ----------------------------------------------------------
    # Grid cells with fewer total pickups than this across the whole dataset are
    # dropped: they are too sparse to model and would swamp the training set
    # with zeros.
    min_cell_pickups: int = 500
    test_fraction: float = 0.2
    random_state: int = 42

    # --- Artifacts ----------------------------------------------------------
    artifacts_dir: Path = BACKEND_DIR / "artifacts"
    data_dir: Path = BACKEND_DIR / "data"

    # --- Copilot (LLM) ------------------------------------------------------
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    copilot_timeout_seconds: float = 20.0

    # --- API ----------------------------------------------------------------
    cors_origins: str = (
        "http://localhost:5173,http://localhost:4173,http://localhost:3000,"
        "http://127.0.0.1:5173,http://127.0.0.1:4173,http://127.0.0.1:3000"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def model_path(self) -> Path:
        return self.artifacts_dir / "demand_model.joblib"

    @property
    def metrics_path(self) -> Path:
        return self.artifacts_dir / "model_metrics.json"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
