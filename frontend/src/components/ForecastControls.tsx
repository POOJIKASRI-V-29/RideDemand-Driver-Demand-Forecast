import type { AppConfig, ForecastQuery } from "../types/demand";
import { formatHour } from "../lib/format";

interface Props {
  config: AppConfig;
  query: ForecastQuery;
  onChange: (next: ForecastQuery) => void;
  onPredict: () => void;
  loading: boolean;
  lastUpdated: string | null;
}

/** Day / time / forecast-window selectors and the Predict Demand action. */
export function ForecastControls({
  config,
  query,
  onChange,
  onPredict,
  loading,
  lastUpdated,
}: Props) {
  return (
    <section className="controls">
      <div className="field">
        <label className="field__label" htmlFor="day-select">
          Day
        </label>
        <select
          id="day-select"
          className="field__select"
          value={query.day}
          onChange={(event) => onChange({ ...query, day: event.target.value })}
        >
          {config.days.map((day) => (
            <option key={day} value={day}>
              {day}
            </option>
          ))}
        </select>
      </div>

      <div className="field" style={{ minWidth: 130 }}>
        <label className="field__label" htmlFor="hour-select">
          Time
        </label>
        <select
          id="hour-select"
          className="field__select"
          value={query.hour}
          onChange={(event) => onChange({ ...query, hour: Number(event.target.value) })}
        >
          {config.hours.map((hour) => (
            <option key={hour} value={hour}>
              {formatHour(hour)}
            </option>
          ))}
        </select>
      </div>

      <div className="field" style={{ minWidth: 0 }}>
        <span className="field__label" id="window-label">
          Forecast window
        </span>
        <div className="segment" role="group" aria-labelledby="window-label">
          {config.windows.map((option) => (
            <button
              key={option.value}
              type="button"
              className={
                option.value === query.window ? "segment__btn segment__btn--active" : "segment__btn"
              }
              aria-pressed={option.value === query.window}
              onClick={() => onChange({ ...query, window: option.value })}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="controls__actions">
        <span className="controls__hint">
          {lastUpdated ? `Forecast generated ${lastUpdated}` : "No forecast generated yet"}
        </span>
        <button type="button" className="btn" onClick={onPredict} disabled={loading}>
          {loading && <span className="spinner" aria-hidden="true" />}
          {loading ? "Predicting…" : "Predict Demand"}
        </button>
      </div>
    </section>
  );
}
