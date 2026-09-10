import type { HourlyDemandPoint } from "../types/demand";
import { formatDemand, formatHour } from "../lib/format";

interface Props {
  profile: HourlyDemandPoint[];
  selectedHour: number;
  day: string;
}

/**
 * City-wide predicted demand across the 24 hours of the selected day.
 *
 * Every point is a real prediction: the backend runs the model for each hour
 * and sums it over all zones.
 */
export function DemandProfile({ profile, selectedHour, day }: Props) {
  const width = 320;
  const height = 84;
  const max = Math.max(...profile.map((point) => point.total_demand), 1);

  const x = (index: number) => (index / Math.max(profile.length - 1, 1)) * width;
  const y = (value: number) => height - (value / max) * height;

  const line = profile
    .map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(1)} ${y(point.total_demand).toFixed(1)}`)
    .join(" ");
  const area = `${line} L${width} ${height} L0 ${height} Z`;

  const peakIndex = profile.reduce(
    (best, point, index) => (point.total_demand > profile[best].total_demand ? index : best),
    0,
  );
  const selectedIndex = profile.findIndex((point) => point.hour === selectedHour);

  return (
    <div className="card">
      <div className="card__head">
        <span className="card__title">Demand through {day}</span>
        <span className="card__endpoint">GET /api/demand</span>
      </div>
      <div className="card__body">
        <svg
          className="profile__chart"
          viewBox={`0 0 ${width} ${height + 8}`}
          role="img"
          aria-label={`Predicted city-wide demand for each hour of ${day}, peaking at ${formatHour(
            profile[peakIndex]?.hour ?? 0,
          )}`}
        >
          <path d={area} fill="var(--accent)" opacity={0.08} />
          <path d={line} fill="none" stroke="var(--accent)" strokeWidth={2} strokeLinejoin="round" />
          {selectedIndex >= 0 && (
            <line
              x1={x(selectedIndex)}
              x2={x(selectedIndex)}
              y1={0}
              y2={height}
              stroke="#101418"
              strokeWidth={1}
              strokeDasharray="3 3"
              opacity={0.35}
            />
          )}
          <circle
            cx={x(peakIndex)}
            cy={y(profile[peakIndex]?.total_demand ?? 0)}
            r={4}
            fill="#fff"
            stroke="var(--accent)"
            strokeWidth={2.5}
          />
        </svg>
        <div className="profile__axis">
          <span>12 AM</span>
          <span>6 AM</span>
          <span>12 PM</span>
          <span>6 PM</span>
          <span>11 PM</span>
        </div>
        <p className="model__caption">
          Peaks at {formatHour(profile[peakIndex]?.hour ?? 0)} with{" "}
          {formatDemand(profile[peakIndex]?.total_demand ?? 0)} predicted requests/hour across all
          zones. The dashed line marks your selected hour.
        </p>
      </div>
    </div>
  );
}
