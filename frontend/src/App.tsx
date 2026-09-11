import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api } from "./services/api";
import type {
  AppConfig,
  CopilotResponse,
  DemandResponse,
  ForecastQuery,
  HotspotsResponse,
  ModelInfo,
  RecommendationResponse,
} from "./types/demand";

import { DemandMap } from "./components/DemandMap";
import { DemandProfile } from "./components/DemandProfile";
import { DemandSummary } from "./components/DemandSummary";
import { DriverCopilot } from "./components/DriverCopilot";
import { EmptyState } from "./components/EmptyState";
import { ErrorState } from "./components/ErrorState";
import { ForecastControls } from "./components/ForecastControls";
import { Header } from "./components/Header";
import { HotspotList } from "./components/HotspotList";
import { LoadingState } from "./components/LoadingState";
import { MapLegend } from "./components/MapLegend";
import { RecommendationCard } from "./components/RecommendationCard";
import { Sidebar } from "./components/Sidebar";

const HOTSPOT_LIMIT = 8;

type Status = "empty" | "loading" | "ready" | "error";

interface Forecast {
  demand: DemandResponse;
  hotspots: HotspotsResponse;
  recommendation: RecommendationResponse;
}

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);

  const [query, setQuery] = useState<ForecastQuery>({ day: "Friday", hour: 19, window: 60 });
  const [status, setStatus] = useState<Status>("empty");
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedZoneId, setSelectedZoneId] = useState<number | null>(null);
  const [focusNonce, setFocusNonce] = useState(0);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);

  const [copilot, setCopilot] = useState<CopilotResponse | null>(null);
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [copilotError, setCopilotError] = useState<string | null>(null);

  /** Guards against a slow earlier request overwriting a newer one. */
  const requestId = useRef(0);

  useEffect(() => {
    Promise.all([api.getConfig(), api.getModel()])
      .then(([loadedConfig, loadedModel]) => {
        setConfig(loadedConfig);
        setModelInfo(loadedModel);
        setQuery((current) => ({
          ...current,
          day: loadedConfig.days.includes(current.day) ? current.day : loadedConfig.days[0],
        }));
      })
      .catch((cause: unknown) => {
        setBootError(
          cause instanceof ApiError
            ? cause.message
            : "Could not load the application configuration.",
        );
      });
  }, []);

  const loadCopilot = useCallback(async (target: ForecastQuery, id: number) => {
    setCopilotLoading(true);
    setCopilotError(null);
    try {
      const response = await api.getCopilot(target);
      if (requestId.current === id) setCopilot(response);
    } catch (cause: unknown) {
      if (requestId.current === id) {
        setCopilot(null);
        setCopilotError(
          cause instanceof ApiError ? cause.message : "The copilot briefing is unavailable.",
        );
      }
    } finally {
      if (requestId.current === id) setCopilotLoading(false);
    }
  }, []);

  const predict = useCallback(
    async (target: ForecastQuery) => {
      const id = ++requestId.current;
      setStatus("loading");
      setError(null);

      try {
        const [demand, hotspots, recommendation] = await Promise.all([
          api.getDemand(target),
          api.getHotspots(target, HOTSPOT_LIMIT),
          api.getRecommendation(target),
        ]);
        if (requestId.current !== id) return;

        if (demand.zones.length === 0) {
          setForecast(null);
          setStatus("empty");
          return;
        }

        setForecast({ demand, hotspots, recommendation });
        setModelInfo(demand.model_info);
        setSelectedZoneId(recommendation.zone.zone_id);
        setGeneratedAt(
          new Date(demand.generated_at).toLocaleTimeString("en-US", {
            hour: "numeric",
            minute: "2-digit",
            second: "2-digit",
          }),
        );
        setStatus("ready");
        void loadCopilot(target, id);
      } catch (cause: unknown) {
        if (requestId.current !== id) return;
        setError(
          cause instanceof ApiError ? cause.message : "An unexpected error occurred.",
        );
        setStatus("error");
        setCopilot(null);
      }
    },
    [loadCopilot],
  );

  /** Explicit user choice: highlight the zone and pan the map to it. */
  const focusZone = useCallback((zoneId: number) => {
    setSelectedZoneId(zoneId);
    setFocusNonce((current) => current + 1);
  }, []);

  if (bootError) {
    return (
      <div className="boot">
        <ErrorState message={bootError} onRetry={() => window.location.reload()} />
      </div>
    );
  }

  if (!config) {
    return (
      <div className="boot">
        <span className="spinner spinner--dark" aria-hidden="true" />
        Connecting to the RideDemand API…
      </div>
    );
  }

  const demand = forecast?.demand ?? null;
  const zones = demand?.zones ?? [];
  const windowLabel =
    demand?.request.window_label ??
    config.windows.find((option) => option.value === query.window)?.label ??
    "";

  return (
    <div className="app">
      <Sidebar config={config} modelInfo={modelInfo} />

      <div className="workspace">
        <Header config={config} modelInfo={modelInfo} />

        <main className="dashboard">
          <ForecastControls
            config={config}
            query={query}
            onChange={setQuery}
            onPredict={() => void predict(query)}
            loading={status === "loading"}
            lastUpdated={status === "ready" ? generatedAt : null}
          />

          <section className="map-panel">
            <DemandMap
              config={config}
              zones={zones}
              selectedZoneId={selectedZoneId}
              focusNonce={focusNonce}
              onSelectZone={focusZone}
              muted={status === "loading"}
              hidden={status === "empty" || status === "error"}
            />

            <MapLegend
              windowLabel={windowLabel}
              maxDemand={demand?.summary.max_zone_demand ?? null}
            />

            {status === "ready" && forecast && (
              <RecommendationCard
                recommendation={forecast.recommendation}
                onFocus={focusZone}
              />
            )}

            {status === "loading" && (
              <div className="map-overlay map-overlay--soft">
                <LoadingState />
              </div>
            )}

            {status === "empty" && (
              <div className="map-overlay">
                <EmptyState onPredict={() => void predict(query)} />
              </div>
            )}

            {status === "error" && error && (
              <div className="map-overlay">
                <ErrorState message={error} onRetry={() => void predict(query)} />
              </div>
            )}
          </section>

          {status === "ready" && forecast && demand && (
            <section className="panel-grid">
              <div className="panel-column">
                <DemandSummary demand={demand} />
                <HotspotList
                  hotspots={forecast.hotspots.hotspots}
                  selectedZoneId={selectedZoneId}
                  onSelectZone={focusZone}
                  windowLabel={windowLabel}
                />
              </div>

              <div className="panel-column">
                <DriverCopilot
                  copilot={copilot}
                  loading={copilotLoading}
                  error={copilotError}
                  onRefresh={() => void loadCopilot(query, requestId.current)}
                  disabled={status !== "ready"}
                />
                <DemandProfile
                  profile={demand.hourly_profile}
                  selectedHour={demand.request.hour}
                  day={demand.request.day}
                />
              </div>
            </section>
          )}
        </main>
      </div>
    </div>
  );
}
