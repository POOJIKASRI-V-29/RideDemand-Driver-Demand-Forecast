import type { AppConfig, ModelInfo } from "../types/demand";

/** "2014-04-01" -> "Apr 14" */
function formatMonth(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

interface Props {
  config: AppConfig;
  modelInfo: ModelInfo | null;
}

/**
 * The dark navigation rail from the RideDemand design. This build ships a
 * single dashboard, so the rail states plainly what the service is running on
 * rather than linking to screens that do not exist.
 */
export function Sidebar({ config, modelInfo }: Props) {
  const usingModel = modelInfo?.source === "gradient_boosting_model";

  /** Only values the backend actually measured; unknowns render as an em dash. */
  const facts: [string, string][] = [
    ["Grid cell", `${config.grid_size}°`],
    ["Zones", modelInfo?.n_zones == null ? "—" : String(modelInfo.n_zones)],
    [
      "Trained on",
      modelInfo?.train_start && modelInfo.train_end
        ? `${formatMonth(modelInfo.train_start)}–${formatMonth(modelInfo.train_end)}`
        : "—",
    ],
    ["Test MAE", modelInfo?.mae == null ? "—" : modelInfo.mae.toFixed(3)],
  ];

  return (
    <aside className="rail">
      <div className="rail__brand">
        <span aria-hidden="true" style={{ fontSize: 19, lineHeight: 1 }}>
          🚕
        </span>
        RideDemand
      </div>

      <nav className="rail__section" aria-label="Workspace">
        <div className="rail__label">WORKSPACE</div>
        <span className="rail__item rail__item--active" aria-current="page">
          <span className="rail__bar" />
          Demand Forecast
        </span>
      </nav>

      <div className="rail__facts">
        <div className="rail__facts-title">FORECAST BASIS</div>
        {facts.map(([label, value]) => (
          <div className="rail__fact" key={label}>
            <span>{label}</span>
            <span className="rail__fact-value">{value}</span>
          </div>
        ))}
      </div>

      <div className="rail__foot">
        <p className="rail__note">
          Forecasts come from historical trip records, not live traffic or live rider demand.
        </p>
        <div className="rail__status">
          <span className={usingModel ? "rail__status-dot" : "rail__status-dot rail__status-dot--off"} />
          <div className="rail__status-text">
            <div className="rail__status-title">
              {usingModel ? "Model serving" : "Historical baseline"}
            </div>
            <div className="rail__status-sub">
              {modelInfo?.n_zones == null ? "—" : modelInfo.n_zones} zones · {config.grid_size}°
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
