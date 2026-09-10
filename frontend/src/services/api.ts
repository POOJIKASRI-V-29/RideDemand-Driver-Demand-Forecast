/**
 * The single place the frontend talks to the backend.
 *
 * Every displayed number originates from one of these calls; the UI performs no
 * prediction, ranking or scoring of its own.
 */
import type {
  AppConfig,
  CopilotResponse,
  DemandResponse,
  ForecastQuery,
  HotspotsResponse,
  ModelInfo,
  RecommendationResponse,
} from "../types/demand";

// 127.0.0.1 rather than "localhost": a local uvicorn binds IPv4 only, while a
// browser resolving "localhost" may prefer ::1 and fail to connect. Docker
// publishes both stacks, and Compose passes its own VITE_API_BASE_URL anyway.
const DEFAULT_BASE_URL = "http://127.0.0.1:8000";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE_URL).replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(
      "Could not reach the RideDemand API. Check that the backend is running.",
      0,
    );
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}.`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body?.detail) && body.detail[0]?.msg) {
        detail = String(body.detail[0].msg);
      }
    } catch {
      /* the body was not JSON; keep the status-based message */
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}

function forecastParams({ day, hour, window }: ForecastQuery): string {
  return new URLSearchParams({
    day,
    hour: String(hour),
    window: String(window),
  }).toString();
}

export const api = {
  getConfig: () => request<AppConfig>("/api/config"),

  getModel: () => request<ModelInfo>("/api/model"),

  getDemand: (query: ForecastQuery) =>
    request<DemandResponse>(`/api/demand?${forecastParams(query)}`),

  getHotspots: (query: ForecastQuery, limit = 8) =>
    request<HotspotsResponse>(`/api/hotspots?${forecastParams(query)}&limit=${limit}`),

  getRecommendation: (query: ForecastQuery) =>
    request<RecommendationResponse>(`/api/recommendation?${forecastParams(query)}`),

  getCopilot: (query: ForecastQuery) =>
    request<CopilotResponse>("/api/copilot", {
      method: "POST",
      body: JSON.stringify({ day: query.day, hour: query.hour, window: query.window }),
    }),
};
