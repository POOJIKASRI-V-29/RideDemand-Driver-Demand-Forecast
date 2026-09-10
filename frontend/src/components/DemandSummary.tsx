import type { DemandResponse } from "../types/demand";
import { formatDemand, formatHourRange, formatMetric } from "../lib/format";

interface Props {
  demand: DemandResponse;
}

/** Four figures, each taken straight from the forecast response. */
export function DemandSummary({ demand }: Props) {
  const { summary, request, model_info: model } = demand;

  const cells = [
    {
      label: "Peak zone demand",
      value: `${formatDemand(summary.max_zone_demand)} req`,
      hint: request.window_label.toLowerCase(),
    },
    {
      label: "Peak area",
      value: summary.peak_zone_name,
      hint: `busiest of ${summary.zone_count} zones`,
    },
    {
      label: "Busiest hour",
      value: formatHourRange(summary.peak_hour),
      hint: `${request.day} · ${formatDemand(summary.peak_hour_demand)} req/hr city-wide`,
    },
    {
      label: "Model error (MAE)",
      value: formatMetric(model.mae),
      hint: model.mae == null ? "baseline mode" : "req/hr per zone · held-out test",
    },
  ];

  return (
    <div className="summary">
      {cells.map((cell) => (
        <div className="summary__cell" key={cell.label}>
          <div className="summary__label">{cell.label}</div>
          <div className="summary__value">{cell.value}</div>
          <div className="summary__hint">{cell.hint}</div>
        </div>
      ))}
    </div>
  );
}
