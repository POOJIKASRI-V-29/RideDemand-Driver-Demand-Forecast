# RideDemand — Ride-Hailing Demand Heatmap Predictor

A driver-facing dashboard that predicts where ride requests are most likely to come from,
for a chosen day, hour and forecast window, and recommends where to position next.

Historical trip records → hourly aggregation over a configurable geographic grid → PostgreSQL →
a gradient boosting model → FastAPI → a React dashboard with a real Leaflet map.

> **Every number in this application is computed.** Model error, demand figures, hotspot
> rankings and the recommendation all come from the pipeline below. Where something could not
> be derived honestly from the data — travel time, distance to the driver, prediction
> confidence — it is not shown at all. See [Assumptions](#assumptions) and
> [Limitations](#limitations).

---

## Table of contents

- [Problem statement](#problem-statement)
- [Solution](#solution)
- [Features](#features)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Dataset](#dataset)
- [Preprocessing](#preprocessing)
- [Geographic grid](#geographic-grid)
- [ML approach](#ml-approach)
- [Evaluation](#evaluation)
- [Forecast windows](#forecast-windows)
- [Driver Copilot](#driver-copilot)
- [API documentation](#api-documentation)
- [Database structure](#database-structure)
- [Environment variables](#environment-variables)
- [Local setup](#local-setup)
- [Docker setup](#docker-setup)
- [Testing](#testing)
- [Assumptions](#assumptions)
- [Limitations](#limitations)
- [Future improvements](#future-improvements)

---

## Problem statement

A driver between fares has one decision to make: *where do I go now?* Getting it wrong means
circling empty streets while requests come in three neighbourhoods away. Drivers build this
intuition over months, it does not transfer between cities, and it is invisible to anyone new.

Demand is not uniform in space or time. It concentrates in particular blocks, at particular
hours, on particular days — and that pattern is recorded in historical trip data that
individual drivers have no way to read.

## Solution

RideDemand turns that history into a forecast a driver can act on:

1. Aggregate historical pickups into a **configurable latitude/longitude grid**, by hour.
2. Train a model to predict pickups per cell for a given weekday and hour.
3. Serve those predictions through a REST API that also **ranks** the zones and **picks** the
   best one.
4. Render them as a heatmap on a real map, with a ranked list, a recommended position, and a
   plain-language briefing.

The frontend performs no prediction, ranking or scoring — it renders what the API returns, so
the map, the list, the recommendation and the copilot can never disagree with each other.

## Features

| # | Feature | Where |
|---|---------|-------|
| 1 | Day selector | `ForecastControls.tsx` |
| 2 | Time selector (24 hours) | `ForecastControls.tsx` |
| 3 | Forecast window selector (30 / 60 / 120 min) | `ForecastControls.tsx` |
| 4 | Predict Demand button → real API request | `App.tsx` → `services/api.ts` |
| 5 | Real Leaflet map with OpenStreetMap tiles | `DemandMap.tsx` |
| 6 | Predicted demand heatmap (one rectangle per grid cell) + markers for the busiest cells | `DemandMap.tsx` |
| 7 | Demand legend | `MapLegend.tsx` |
| 8 | Recommended Position card | `RecommendationCard.tsx` ← `GET /api/recommendation` |
| 9 | Ranked Top Demand Areas | `HotspotList.tsx` ← `GET /api/hotspots` |
| 10 | Driver Copilot (LLM, with deterministic fallback) | `DriverCopilot.tsx` ← `POST /api/copilot` |
| 11 | Loading state | `LoadingState.tsx` |
| 12 | Empty state | `EmptyState.tsx` |
| 13 | Error state | `ErrorState.tsx` |
| 14 | PostgreSQL persistence | `models.py`, `scripts/load_db.py` |
| 15 | REST API | `app/api/` |
| 16 | Docker Compose | `docker-compose.yml` |
| 17 | This README | — |
| 18 | Backend tests | `backend/tests/` |

Two further panels show only measured values: an hourly demand profile for the selected day
(24 real predictions summed across zones) and a pipeline card reporting the model's actual
test metrics.

## Architecture

```mermaid
flowchart TB
    subgraph offline["Offline pipeline (scripts/)"]
        A["Uber TLC FOIL 2014<br/>raw pickups CSV"] --> B["prepare_data.py<br/>bbox filter · grid assignment<br/>hourly aggregation"]
        B --> C["load_db.py<br/>bulk COPY"]
        C --> DB[("PostgreSQL")]
        DB --> D["train_model.py<br/>dense panel · chronological split<br/>HistGradientBoostingRegressor"]
        D --> DB
        D --> E["artifacts/<br/>demand_model.joblib<br/>model_metrics.json"]
    end

    subgraph online["Request path"]
        DB --> F["demand_service<br/>features → predict → rank"]
        E --> F
        F --> G["recommendation_service"]
        F --> H["copilot_service"]
        H -->|"key set"| I["Claude API"]
        H -->|"no key"| J["deterministic template"]
        F --> API["FastAPI<br/>/api/demand · /api/hotspots<br/>/api/recommendation · /api/copilot"]
        G --> API
        H --> API
    end

    API --> UI["React + Vite + TypeScript"]
    UI --> MAP["React-Leaflet · OpenStreetMap"]
```

The critical property: `demand_service.predict_zones()` is the single prediction path. The
map, the hotspot list, the recommendation and the copilot all read from it.

## Tech stack

| Layer | Choice |
|-------|--------|
| Frontend | React 19, Vite, TypeScript, plain CSS, React-Leaflet / Leaflet |
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2.0, Pydantic v2 |
| Database | PostgreSQL 16 |
| Data / ML | pandas, NumPy, scikit-learn, joblib |
| Infrastructure | Docker, Docker Compose, nginx (static frontend) |
| AI | Anthropic Claude (optional), deterministic fallback otherwise |

## Dataset

**[FiveThirtyEight — `uber-tlc-foil-response`](https://github.com/fivethirtyeight/uber-tlc-foil-response)**:
raw Uber pickup records that New York City's Taxi & Limousine Commission released in response
to a Freedom of Information Law request. Publicly available and freely usable.

The **2014** files are used specifically because they carry raw latitude/longitude for every
pickup. Later TLC releases publish anonymised zone IDs instead, which cannot support a
geographic grid.

### Fields

| Column | Type | Used for |
|--------|------|----------|
| `Date/Time` | `M/D/YYYY H:MM:SS` | Hour of day, day of week, weekend flag |
| `Lat` | float | Grid cell latitude |
| `Lon` | float | Grid cell longitude |
| `Base` | string | Not used — the dispatching base is irrelevant to demand location |

One row is one pickup. There is no drop-off, fare, distance or duration in this dataset —
which is precisely why this project shows none of those.

### Volume in the default configuration (April–June 2014)

| Stage | Rows |
|-------|------|
| Raw pickups downloaded | 1,880,795 |
| Inside the study bounding box | 1,853,945 (98.6%) |
| Non-empty (cell, date, hour) slots | 263,048 |
| Retained after dropping sparse cells | 210,888 slots across **166 zones** (96.9% of all pickups) |
| Dense training panel (zeros filled in) | 362,544 rows |

Raw CSVs are ~87 MB and are **not committed** — `.gitignore` excludes `backend/data/` and
`backend/artifacts/`. `scripts/prepare_data.py` re-downloads them on demand.

## Preprocessing

`backend/scripts/prepare_data.py`:

1. **Download** the requested monthly CSVs, caching them in `backend/data/raw/`.
2. **Parse** `Date/Time` with an explicit format; drop rows with an unparseable timestamp or a
   missing coordinate.
3. **Clip** to the study bounding box (40.55–40.92 N, −74.10 – −73.70 W), which removes stray
   coordinates far outside the city.
4. **Assign a grid cell** to every pickup (see below).
5. **Aggregate** to `(cell, date, hour)` counts and derive `day_of_week` and `is_weekend`.
6. **Select zones**: drop cells with fewer than `MIN_CELL_PICKUPS` (default 500) total pickups.
   They are too sparse to model and would flood the training set with near-empty rows. At the
   default this keeps 166 of 1,138 cells — 96.9% of all pickups.
7. **Label** each cell with the nearest entry from a bundled table of ~70 neighbourhood
   centroids, plus a compass suffix when several cells map to the same name (`SoHo`, `SoHo E`).
8. **Write** `zones.csv` and `observations.csv` to `backend/data/processed/`.

`scripts/load_db.py` then truncates and reloads the tables, streaming observations through
PostgreSQL `COPY`. The load is idempotent — re-running after a grid-size change leaves no
stale rows.

## Geographic grid

One definition, in `backend/app/ml/grid.py`, used by preprocessing, training, the API and
(through the API payload) the frontend:

```python
grid_lat = floor(latitude  / grid_size) * grid_size
grid_lng = floor(longitude / grid_size) * grid_size
```

A cell is identified by its **south-west corner**; values are rounded to 6 decimals so
floating-point noise cannot split one cell into two. The API returns each cell's corner, its
centre and its `[[south, west], [north, east]]` bounds, and the map draws exactly those
rectangles — the squares on screen are the cells the model predicted for.

`GRID_SIZE` defaults to **0.01°** (≈1.11 km north–south, ≈0.84 km east–west at this latitude).
It is configurable; change it and re-run the full pipeline so every stage agrees.

## ML approach

**`sklearn.ensemble.HistGradientBoostingRegressor`** — scikit-learn's histogram-based gradient
boosting, chosen over `GradientBoostingRegressor` because it fits 286k rows in seconds rather
than minutes with equivalent behaviour.

### The dense panel

Predicting only on hours that saw pickups would teach the model that demand is never zero.
The trainer expands the observations into every `(zone, date, hour)` combination and fills the
gaps with 0 — **41.8%** of the resulting 362,544 rows. Those zeros are real signal.

### Residual target

The historical mean for a `(zone, weekday, hour)` slot is already a strong predictor of
aggregated counts. Rather than asking the model to reproduce it, the model predicts the
**residual against it**:

```
predicted_demand = max(0, zone_hour_mean + estimator(features))
```

This was not a guess: a direct-target model scored **1.8194** MAE on inner validation against
the baseline's **1.8168** — it could not beat the average it was handed as a feature. The
residual formulation scored **1.7947**. Both numbers came from the validation split, before
the test split was touched.

### Features

| Feature | Description |
|---------|-------------|
| `hour` | 0–23 |
| `day_of_week` | 0 = Monday |
| `is_weekend` | 1 for Saturday/Sunday |
| `grid_lat`, `grid_lng` | Cell corner — lets the model learn spatial structure |
| `zone_hour_mean` | Historical mean for this (zone, weekday, hour) — also the baseline |
| `zone_hour_median` | Historical median for the same slot |
| `zone_hourofday_mean` | Mean for (zone, hour) pooled across weekdays — less noisy |
| `zone_dow_mean` | Mean for (zone, weekday) pooled across hours |
| `zone_mean` | Mean for the zone overall |
| `zone_recent_hour_mean` | Mean for (zone, hour) over the last 14 training days |

**All historical features are computed from the training dates only** and stored in
`zone_hour_stats`, which the API reads back at request time. Training and serving therefore
see identical numbers, and no test-period information reaches the model.

### Splitting and selection

- **Test split**: the most recent 20% of dates, held out entirely. A random split would leak
  future information into the past.
- **Model selection**: four candidate configurations (absolute-error, squared-error and
  Poisson losses at two regularisation settings) are compared on an *inner* validation split
  carved from the training dates. The winner is refitted on the full training split.
- The test split is used **once**, for the reported metrics.

## Evaluation

Measured by `scripts/train_model.py` on the held-out test split (2014-06-12 → 2014-06-30,
75,696 rows), and stored in `model_metadata` and `artifacts/model_metrics.json`:

| Metric | Value |
|--------|-------|
| **MAE** | **1.7705** pickups/hour per zone |
| RMSE | 4.2641 |
| R² | 0.8978 |
| Baseline MAE (historical mean for the same slot) | 1.7838 |
| Improvement over baseline | **0.75%** |
| Training rows | 286,848 (2014-04-01 → 2014-06-11) |
| Test rows | 75,696 |
| Zones | 166 |

**Read this honestly.** The model beats the historical-average baseline, but by 0.75% —
a real improvement, chosen on validation and confirmed on a split the model never saw, and a
small one. For hourly counts aggregated over ~1 km cells, the per-slot historical average is
already close to the best available predictor, and there is little structure left for a
gradient booster to find. R² of 0.90 reflects the strong, easily-learned variation between a
Manhattan cell at 7 PM and an outer-borough cell at 4 AM; it is not evidence of a
sophisticated model.

The API reports both figures side by side (`mae` and `baseline_mae` on `/api/model`, and both
rows in the dashboard's pipeline card) precisely so the model's contribution stays visible
rather than assumed. Re-running the pipeline reproduces these numbers exactly —
`random_state` is fixed.

## Forecast windows

The source data is aggregated per calendar hour, so the three windows map onto hourly
predictions as follows:

| Window | Computation |
|--------|-------------|
| Next 30 min | Half the predicted hourly rate — **assumes demand is uniform within the hour** |
| Next 60 min | The predicted hourly rate as-is |
| Next 2 hours | The selected hour plus the following hour, both predicted, summed |

Each zone carries both `predicted_demand` (the window total) and `predicted_per_hour`, so the
rate is always visible alongside the window figure. This is an approximation, and the 30-minute
uniformity assumption in particular is a simplification — real demand is not flat inside an
hour. Sub-hourly forecasting would need sub-hourly aggregation, which this dataset supports
but this build does not implement.

## Driver Copilot

`POST /api/copilot` returns a short, plain-language briefing over the forecast.

**With an API key** (`ANTHROPIC_API_KEY`): the exact prediction figures are passed to Claude,
whose system prompt forbids inventing numbers, mentioning distance, travel time, earnings or
ETA, and stating any confidence figure. The model phrases values it is given; it never
produces one.

**Without a key** — or if the API call fails, times out or is declined: a deterministic
template renders the same figures. The application is fully functional either way.

The response always reports which path was used (`source: "llm" | "fallback"`) and returns the
`grounded_on` figures the text was written from, so the text can be checked against the
prediction. The dashboard shows the provenance in the copilot card's footer.

> The deterministic fallback is exercised by the test suite and verified end to end. The live
> LLM branch is covered by tests with a stubbed client; it was not exercised against the real
> API during development because no key was configured.

## API documentation

Interactive docs at `http://localhost:8000/docs` (OpenAPI at `/openapi.json`).

Shared query parameters:

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `day` | string \| int | `Friday` | `"Friday"`, `"friday"`, `"fri"` or `0`–`6` (0 = Monday) |
| `hour` | int | `19` | 0–23 |
| `window` | int | `60` | `30`, `60` or `120` |

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Service health: database reachability, whether a model is loaded, row counts, whether the LLM copilot is configured. Returns `degraded` when the API is up but cannot predict. |
| `GET /api/config` | Grid size, map centre/bounds, and the selector options — so the frontend hardcodes no geography |
| `GET /api/model` | Model provenance and its **measured** metrics |
| `GET /api/demand` | Predicted demand for every zone, plus the day's 24-hour profile and a summary. `limit` trims the list |
| `GET /api/hotspots` | The top `limit` zones (default 8), ranked |
| `GET /api/recommendation` | The single best zone, with the figures justifying it |
| `GET`/`POST /api/copilot` | The driver briefing |

**Errors**: `422` for an invalid day, hour, window or limit, with a message naming the valid
values. `503` when the database holds no zones or statistics — a server-state problem
(the pipeline has not been run), not a bad request.

<details>
<summary><code>GET /api/hotspots?day=Friday&amp;hour=19&amp;window=60&amp;limit=2</code></summary>

```json
{
  "request": {
    "day": "Friday", "day_of_week": 4, "hour": 19,
    "window_minutes": 60, "window_label": "Next 60 min", "grid_size": 0.01
  },
  "generated_at": "2026-09-10T11:41:01.512Z",
  "model_info": {
    "source": "gradient_boosting_model",
    "algorithm": "sklearn.ensemble.HistGradientBoostingRegressor",
    "target": "residual of ride_count against zone_hour_mean",
    "mae": 1.7705, "baseline_mae": 1.7838, "r2": 0.8978,
    "test_start": "2014-06-12", "test_end": "2014-06-30"
  },
  "hotspots": [
    {
      "zone_id": 1, "name": "Midtown East",
      "grid_lat": 40.75, "grid_lng": -73.98, "grid_size": 0.01,
      "center": { "lat": 40.755, "lng": -73.975 },
      "bounds": [[40.75, -73.98], [40.76, -73.97]],
      "predicted_demand": 109.55, "predicted_per_hour": 109.55,
      "intensity": 1.0, "level": "very_high",
      "historical_samples": 10, "historical_mean_per_hour": 110.2
    }
  ]
}
```
</details>

`intensity` is each zone's demand relative to the busiest zone **in that same response**, and
`level` bands it for the legend. Neither is a confidence score.

## Database structure

```mermaid
erDiagram
    zones ||--o{ demand_observations : has
    zones ||--o{ zone_hour_stats : has

    zones {
        int id PK
        float grid_lat "SW corner"
        float grid_lng "SW corner"
        float grid_size
        float center_lat
        float center_lng
        string name "approximate label"
        int total_pickups
    }
    demand_observations {
        int id PK
        int zone_id FK
        date obs_date
        int hour
        int day_of_week
        int is_weekend
        int ride_count
    }
    zone_hour_stats {
        int id PK
        int zone_id FK
        int day_of_week
        int hour
        float mean_demand "the baseline"
        float median_demand
        float max_demand
        int sample_count
        float hourofday_mean
        float dow_mean
        float zone_mean_demand
        float recent_hour_mean
    }
    model_metadata {
        int id PK
        string algorithm
        datetime trained_at
        string features
        float mae "measured"
        float rmse "measured"
        float r2 "measured"
        float baseline_mae "measured"
        int n_train_rows
        int n_test_rows
        date test_start
        date test_end
        string dataset_name
        float grid_size
    }
```

Row counts in the default configuration: 166 zones, 210,888 observations, 27,888 stat rows
(166 × 7 × 24), 1 model metadata row.

`zones` is uniquely keyed on `(grid_lat, grid_lng, grid_size)`; `demand_observations` on
`(zone_id, obs_date, hour)`; `zone_hour_stats` on `(zone_id, day_of_week, hour)`.

## Environment variables

Copy `.env.example` to `.env`. **No secrets are committed.**

Every variable has a working default in `backend/app/config.py`, so the shipped `.env.example`
runs the project as-is. Docker Compose passes the whole `.env` into the backend and pipeline
containers, so anything set locally also takes effect there — the one exception is
`DATABASE_URL`, which Compose overrides to reach the database as `postgres` instead of
`localhost`.

**Database**

| Variable | Default | Purpose |
|----------|---------|---------|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `ridedemand` | Credentials for the Compose database |
| `POSTGRES_PORT` | `5432` | Host port the database is published on |
| `DATABASE_URL` | `postgresql+psycopg://ridedemand:ridedemand@localhost:5432/ridedemand` | Connection string used by the backend and scripts |
| `TEST_DATABASE_URL` | `DATABASE_URL` + `_test` | Test database. Derived automatically; set it only to send tests elsewhere |

**Grid and study area**

| Variable | Default | Purpose |
|----------|---------|---------|
| `GRID_SIZE` | `0.01` | Grid cell edge in degrees |
| `MIN_CELL_PICKUPS` | `500` | Drop cells sparser than this |
| `CITY_NAME` | `New York City` | Shown in the dashboard header |
| `BBOX_MIN_LAT` / `BBOX_MAX_LAT` | `40.55` / `40.92` | Latitude bounds pickups are clipped to |
| `BBOX_MIN_LNG` / `BBOX_MAX_LNG` | `-74.10` / `-73.70` | Longitude bounds |
| `MAP_CENTER_LAT` / `MAP_CENTER_LNG` | `40.7420` / `-73.9800` | Initial map centre |
| `MAP_DEFAULT_ZOOM` | `12` | Initial Leaflet zoom |

**Data and training**

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATA_MONTHS` | `apr14 may14 jun14` | Which monthly files to ingest |
| `TEST_FRACTION` | `0.2` | Share of the most recent dates held out for testing |
| `RANDOM_STATE` | `42` | Fixed so training is reproducible |

**API and frontend**

| Variable | Default | Purpose |
|----------|---------|---------|
| `BACKEND_PORT` / `FRONTEND_PORT` | `8000` / `3000` | Published ports |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Comma-separated allowed origins |
| `VITE_API_BASE_URL` | `http://localhost:8000` | API base, inlined into the bundle at build time |

**Driver Copilot (optional)**

| Variable | Default | Purpose |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | *(empty)* | Blank → deterministic fallback. The app is fully usable either way |
| `ANTHROPIC_MODEL` | `claude-opus-5` | Model used when a key is set |
| `COPILOT_TIMEOUT_SECONDS` | `20` | Request timeout before falling back |

## Local setup

**Prerequisites**: Python 3.12+, Node 20+, PostgreSQL 14+.

```bash
# 1. Database
createdb ridedemand
psql -d postgres -c "CREATE ROLE ridedemand LOGIN PASSWORD 'ridedemand' CREATEDB"
psql -d postgres -c "ALTER DATABASE ridedemand OWNER TO ridedemand"
```

`CREATEDB` lets the test suite create its own `ridedemand_test` database; without it the
database-backed tests skip rather than fail.

```bash
# 2. Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # edit if your database differs

# 3. Pipeline — downloads ~87 MB, then trains. A few minutes on first run.
python -m scripts.prepare_data --months apr14 may14 jun14
python -m scripts.load_db
python -m scripts.train_model

# 4. Serve
uvicorn app.main:app --reload --port 8000
```

```bash
# 5. Frontend, in a second terminal
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

Check `http://localhost:8000/health` — `status: "ok"` with non-zero `zones_loaded` means the
pipeline succeeded.

The API does not have to be started in that order. If no model file exists it serves the
historical-average baseline and says so in `/api/model`, so the app works with step 3 skipped;
and when training later writes the artifact, the running process picks it up automatically —
no restart. Retraining is picked up the same way.

### Useful pipeline options

```bash
python -m scripts.prepare_data --sample-fraction 0.1     # quick smoke run
python -m scripts.prepare_data --grid-size 0.02          # coarser cells
python -m scripts.prepare_data --months apr14 may14 jun14 jul14 aug14 sep14
```

Changing the grid size requires re-running all three scripts, and `GRID_SIZE` must match in
`.env` so the API and frontend agree.

## Docker setup

```bash
cp .env.example .env

docker compose up -d postgres
docker compose --profile setup run --rm pipeline   # download → load → train
docker compose up -d backend frontend
```

- Frontend: <http://localhost:3000>
- API + docs: <http://localhost:8000/docs>

The pipeline is a separate one-shot service on purpose: it downloads raw data and trains a
model, which should not happen on every container restart. It writes into `backend/data/` and
`backend/artifacts/`, both mounted into the backend container.

```bash
docker compose logs -f backend
docker compose down          # stop
docker compose down -v       # stop and delete the database volume
```

If you already run PostgreSQL on 5432, set `POSTGRES_PORT` to a free port (e.g. `5433`) in
`.env` before starting — only the published port changes; the backend reaches the database
over the Compose network on 5432 either way.

> **Verified.** Both images were built and the full stack was run end to end: the pipeline
> service reproduced the metrics in [Evaluation](#evaluation) exactly, `/health` reported
> `ok` with 166 zones and 210,888 observations, and the nginx-served frontend at
> `localhost:3000` completed the whole forecast flow against the containerised API.

## Testing

```bash
cd backend
source .venv/bin/activate
python -m pytest              # 90 tests
```

The suite creates and uses its own test database — `DATABASE_URL` with `_test` appended, so it
follows whichever server you are pointed at — and seeds a small fixture whose expected answers
are obvious by inspection. It never touches development data. If no PostgreSQL server is
reachable, the database-backed tests skip rather than fail.

| File | Covers |
|------|--------|
| `test_health.py` | Health endpoint, config endpoint, model provenance in both model and baseline modes |
| `test_demand.py` | Ranking, intensity banding, grid geometry, all three window computations, hourly profile, day parsing, quiet slots |
| `test_hotspots.py` | Ranking order, `limit`, agreement with `/api/demand`, ranking changing with the window |
| `test_recommendation.py` | Matches the top hotspot, lead and share arithmetic, **asserts no distance/ETA/confidence is ever returned** |
| `test_validation.py` | Invalid day, hour, window and limit across every endpoint; `503` on an empty database |
| `test_copilot.py` | Fallback path, grounding matching the recommendation, LLM path with a stub, graceful degradation on LLM failure, GET/POST agreement |
| `test_grid.py` | Grid maths including negative longitudes and alternative grid sizes, cell labelling, day parsing |
| `test_model.py` | The real trained artifact: non-negative finite predictions, ordering, feature-order match, that saved metrics are real values, and that a model written after startup is picked up without a restart |

### Manual end-to-end verification performed

Open the app → select day/time/window → **Predict Demand** → request succeeds → zones return →
map redraws with heatmap cells and markers → hotspot list updates → recommendation updates →
copilot responds → clicking an area focuses the map → empty state shows before the first
forecast → error state shows when the API is unreachable → loading state shows during the
request → **Try again** recovers once the API is back.

Changing the selectors genuinely changes the forecast: Friday 19:00 over the next 60 minutes
recommends **Midtown East** (109.5 predicted requests), while Saturday 22:00 over the next 2
hours recommends **West Village** (250.5), with the heatmap shifting from Midtown down to the
Village and SoHo. Both the Vite dev server and the containerised nginx build were exercised
this way.

## Assumptions

1. **Sub-hourly windows are interpolated.** The 30-minute window is half the hourly rate,
   assuming uniform demand within the hour. See [Forecast windows](#forecast-windows).
2. **Zone names are approximate.** Each cell is labelled with the nearest of ~70 bundled
   neighbourhood centroids plus a compass suffix. These are convenience labels, not
   authoritative boundaries — nearest-point assignment ignores real neighbourhood and borough
   geometry, so an edge cell may carry a neighbour's name.
3. **Pickups stand in for demand.** The dataset records completed pickups, not requests. Unmet
   demand — riders who requested and cancelled, or never requested because no car was near —
   is invisible, which biases the data toward areas that were already well served.
4. **Sparse cells are excluded.** Cells below `MIN_CELL_PICKUPS` are dropped, so the map covers
   166 busy cells rather than the whole bounding box.
5. **Weekday and hour capture the pattern.** No holiday, weather or event features are used;
   the data covers three months, too short to learn seasonality.
6. **"Demand level" is relative.** `very_high`/`high`/`moderate`/`low` band each zone against
   the busiest zone in the same response. They are not absolute thresholds or confidences.

## Limitations

- **The model's edge over the naive baseline is small** — 0.75% MAE. Reported plainly rather
  than dressed up; both figures are in the API and on the dashboard.
- **The data is from 2014 and is not live.** Forecasts describe historical patterns in New York
  City, not current conditions. Nothing in the app is real-time.
- **No distance, travel time or ETA.** The dataset has no driver location and no trip
  geometry. The recommendation card shows lead over the runner-up, share of the top ten and
  the number of historical observations behind the figure — all computed — instead.
- **No confidence intervals.** A point-estimate regressor produces none, so none is shown.
  `historical_samples` is exposed instead, so a figure resting on 10 observations is visible
  as such.
- **Not evaluated against live outcomes.** There is no predicted-vs-actual tracking; the only
  evaluation is the held-out historical split.
- **Single city, single model.** The grid, bounding box and neighbourhood table are NYC-specific.
- **Desktop-first layout.** The dashboard reflows on a narrow window — the rail becomes a top
  strip and the recommendation becomes a sheet over the map — but there is no dedicated mobile
  experience; the prototype's separate phone layout was out of MVP scope.
- **The LLM copilot path was not exercised against the live API** during development (no key
  available); it is covered by tests with a stubbed client.

## Future improvements

- **Sub-hourly aggregation** to make the 30-minute window a genuine forecast rather than an
  interpolation — the raw data has minute-level timestamps.
- **Richer features** where they can be sourced honestly: weather, public holidays, event
  calendars, and a longer history for seasonality.
- **Calibrated uncertainty** via quantile regression, so the UI could show a range instead of
  a point estimate.
- **Predicted-vs-actual monitoring**, which would make the accuracy claims continuously
  verifiable rather than a one-off split.
- **Spatial smoothing** across neighbouring cells, which the current per-cell model does not do.
- **Real zone geometry** from the official TLC taxi-zone shapefile, replacing approximate
  nearest-centroid labels.
- **Incremental loading** so a new month can be appended without a full reload.
