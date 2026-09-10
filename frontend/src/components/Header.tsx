import type { AppConfig, ModelInfo } from "../types/demand";

interface Props {
  config: AppConfig;
  modelInfo: ModelInfo | null;
}

/** Page title plus a status pill describing what is actually serving predictions. */
export function Header({ config, modelInfo }: Props) {
  const now = new Date();
  const usingModel = modelInfo?.source === "gradient_boosting_model";
  const statusLabel = modelInfo
    ? usingModel
      ? "Model active"
      : "Baseline mode"
    : "Connected";

  return (
    <header className="header">
      <div style={{ minWidth: 0 }}>
        <h1 className="header__title">Demand Forecast</h1>
        <p className="header__sub">
          Predicted ride demand across {config.city_name}, on a {config.grid_size}° grid. Pick a
          day, an hour and a forecast window to see where requests are most likely to come from.
        </p>
      </div>
      <div className="header__meta">
        <div className="header__clock">
          <div className="header__clock-time">
            {now.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}
          </div>
          <div className="header__clock-date">
            {now.toLocaleDateString("en-US", {
              weekday: "short",
              day: "numeric",
              month: "short",
              year: "numeric",
            })}
          </div>
        </div>
        <span className={usingModel || !modelInfo ? "pill" : "pill pill--warn"}>
          <span className="pill__dot" />
          {statusLabel}
        </span>
      </div>
    </header>
  );
}
