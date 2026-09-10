/**
 * Mirrors the FastAPI response schemas in `backend/app/schemas.py`.
 * Nothing here is computed client-side — these are the shapes the API returns.
 */

export type DemandLevel = "low" | "moderate" | "high" | "very_high";
export type PredictionSource = "gradient_boosting_model" | "historical_baseline";

export interface LatLng {
  lat: number;
  lng: number;
}

export interface ZoneDemand {
  zone_id: number;
  name: string;
  grid_lat: number;
  grid_lng: number;
  grid_size: number;
  center: LatLng;
  /** [[south, west], [north, east]] */
  bounds: [number, number][];
  predicted_demand: number;
  predicted_per_hour: number;
  intensity: number;
  level: DemandLevel;
  historical_samples: number;
  historical_mean_per_hour: number;
}

export interface HourlyDemandPoint {
  hour: number;
  total_demand: number;
}

export interface ForecastRequestInfo {
  day: string;
  day_of_week: number;
  hour: number;
  window_minutes: number;
  window_label: string;
  grid_size: number;
}

export interface ModelInfo {
  source: PredictionSource;
  algorithm: string;
  target: string;
  features: string[];
  trained_at?: string | null;
  mae?: number | null;
  rmse?: number | null;
  r2?: number | null;
  baseline_mae?: number | null;
  n_train_rows?: number | null;
  n_test_rows?: number | null;
  n_zones?: number | null;
  train_start?: string | null;
  train_end?: string | null;
  test_start?: string | null;
  test_end?: string | null;
  dataset_name?: string | null;
  grid_size?: number | null;
  note?: string | null;
}

export interface ForecastSummary {
  zone_count: number;
  total_predicted_demand: number;
  max_zone_demand: number;
  peak_zone_name: string;
  peak_hour: number;
  peak_hour_demand: number;
}

export interface DemandResponse {
  request: ForecastRequestInfo;
  generated_at: string;
  model_info: ModelInfo;
  summary: ForecastSummary;
  zones: ZoneDemand[];
  hourly_profile: HourlyDemandPoint[];
}

export interface HotspotsResponse {
  request: ForecastRequestInfo;
  generated_at: string;
  model_info: ModelInfo;
  hotspots: ZoneDemand[];
}

export interface RecommendationReason {
  label: string;
  value: string;
  detail: string;
}

export interface RecommendationResponse {
  request: ForecastRequestInfo;
  generated_at: string;
  model_info: ModelInfo;
  zone: ZoneDemand;
  rank: number;
  lead_over_runner_up: number;
  runner_up_name: string | null;
  share_of_top_zones: number;
  reasons: RecommendationReason[];
}

export interface CopilotResponse {
  request: ForecastRequestInfo;
  generated_at: string;
  message: string;
  source: "llm" | "fallback";
  model: string | null;
  grounded_on: Record<string, string | number>;
}

export interface WindowOption {
  value: number;
  label: string;
}

export interface AppConfig {
  city_name: string;
  grid_size: number;
  map_center: LatLng;
  map_default_zoom: number;
  bounds: [number, number][];
  days: string[];
  hours: number[];
  windows: WindowOption[];
  has_model: boolean;
  has_llm_copilot: boolean;
}

/** The parameters the three forecast selectors produce. */
export interface ForecastQuery {
  day: string;
  hour: number;
  window: number;
}
