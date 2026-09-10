import type { RecommendationResponse } from "../types/demand";
import { LEVEL_COLOR, LEVEL_LABEL, formatDemand } from "../lib/format";

interface Props {
  recommendation: RecommendationResponse;
  onFocus: (zoneId: number) => void;
}

/**
 * The recommended position. The backend picks the zone and supplies the
 * supporting figures — this component only renders them.
 *
 * There is deliberately no distance, travel time or confidence score: the
 * dataset carries no driver location and the model produces no calibrated
 * confidence, so none of those can be shown honestly.
 */
export function RecommendationCard({ recommendation, onFocus }: Props) {
  const { zone, reasons, request } = recommendation;

  return (
    <div className="rec">
      <div className="rec__head">
        <div className="rec__kicker">
          <span aria-hidden="true">🔥</span>
          Recommended position
        </div>
        <button
          type="button"
          className="rec__name"
          onClick={() => onFocus(zone.zone_id)}
          style={{ background: "none", border: "none", padding: 0, cursor: "pointer", textAlign: "left" }}
        >
          {zone.name}
        </button>
        <div className="rec__figure">
          <span className="rec__figure-value">{formatDemand(zone.predicted_demand)}</span>
          <span className="rec__figure-unit">
            predicted requests · {request.window_label.toLowerCase()}
          </span>
        </div>
        <span className="badge" style={{ background: LEVEL_COLOR[zone.level] }}>
          {LEVEL_LABEL[zone.level].toUpperCase()}
        </span>
      </div>

      <div className="rec__reasons">
        {reasons.map((reason) => (
          <div className="rec__reason" key={reason.label} title={reason.detail}>
            <div className="rec__reason-label">{reason.label}</div>
            <div className="rec__reason-value">{reason.value}</div>
          </div>
        ))}
      </div>

      <p className="rec__foot">
        Cell {zone.grid_lat.toFixed(2)}, {zone.grid_lng.toFixed(2)} · {zone.grid_size}° grid ·{" "}
        {formatDemand(zone.predicted_per_hour)} requests/hour
      </p>
    </div>
  );
}
