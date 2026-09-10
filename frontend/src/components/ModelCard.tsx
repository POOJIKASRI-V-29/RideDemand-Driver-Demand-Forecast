import type { ModelInfo } from "../types/demand";
import { formatCount, formatDate, formatMetric } from "../lib/format";

interface Props {
  model: ModelInfo;
}

/**
 * What produced the numbers on this page.
 *
 * Every value shown comes from `model_metadata`, written by the training
 * script from a held-out test split. Nothing here is a marketing figure.
 */
export function ModelCard({ model }: Props) {
  const isBaseline = model.source === "historical_baseline";

  const rows: [string, string][] = isBaseline
    ? [
        ["Predictor", "Historical mean"],
        ["Grouping", "zone × weekday × hour"],
      ]
    : [
        ["Estimator", model.algorithm.split(".").pop() ?? model.algorithm],
        ["Test MAE", `${formatMetric(model.mae)} req/hr`],
        ["Baseline MAE", `${formatMetric(model.baseline_mae)} req/hr`],
        ["Test R²", model.r2 == null ? "—" : model.r2.toFixed(3)],
        ["Train rows", formatCount(model.n_train_rows)],
        ["Test rows", formatCount(model.n_test_rows)],
        ["Test period", `${formatDate(model.test_start)} – ${formatDate(model.test_end)}`],
      ];

  return (
    <div className="card">
      <div className="card__head">
        <span className="card__title">Prediction pipeline</span>
        <span className="card__endpoint">GET /api/model</span>
      </div>
      <div className="card__body">
        {rows.map(([label, value]) => (
          <div className="model__row" key={label}>
            <span>{label}</span>
            <span className="model__value">{value}</span>
          </div>
        ))}
        <p className="model__caption">
          {isBaseline
            ? model.note ??
              "No trained model is loaded, so predictions are historical averages."
            : `MAE is the mean absolute error in requests per hour per zone, measured on dates the model never saw during training. The baseline row is the historical average for the same slot, shown so the model's contribution is visible.`}
        </p>
        {model.dataset_name && (
          <p className="model__caption" style={{ color: "var(--fainter)" }}>
            Data: {model.dataset_name}
          </p>
        )}
      </div>
    </div>
  );
}
