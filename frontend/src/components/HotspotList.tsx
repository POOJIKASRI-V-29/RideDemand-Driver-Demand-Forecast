import type { ZoneDemand } from "../types/demand";
import { LEVEL_COLOR, formatDemand } from "../lib/format";

interface Props {
  hotspots: ZoneDemand[];
  selectedZoneId: number | null;
  onSelectZone: (zoneId: number) => void;
  windowLabel: string;
}

/** Ranked top demand areas, ordered by the backend. */
export function HotspotList({ hotspots, selectedZoneId, onSelectZone, windowLabel }: Props) {
  return (
    <div className="card">
      <div className="card__head">
        <span className="card__title">Top Demand Areas</span>
        <span className="card__note">Select an area to focus the map</span>
      </div>

      <div className="hotspots__head">
        <span>Rank</span>
        <span>Area</span>
        <span>Demand</span>
        <span style={{ textAlign: "right" }}>Req</span>
        <span style={{ textAlign: "right" }}>Per hr</span>
      </div>

      {hotspots.map((zone, index) => (
        <button
          type="button"
          key={zone.zone_id}
          className={
            zone.zone_id === selectedZoneId ? "hotspots__row hotspots__row--active" : "hotspots__row"
          }
          onClick={() => onSelectZone(zone.zone_id)}
          aria-label={`${zone.name}, rank ${index + 1}, ${formatDemand(
            zone.predicted_demand,
          )} predicted requests over the ${windowLabel.toLowerCase()}`}
        >
          <span className="hotspots__rank">{index + 1}</span>
          <span className="hotspots__name">{zone.name}</span>
          <span className="hotspots__track">
            <span
              className="hotspots__fill"
              style={{
                width: `${Math.max(zone.intensity * 100, 2)}%`,
                background: LEVEL_COLOR[zone.level],
              }}
            />
          </span>
          <span className="hotspots__num">{formatDemand(zone.predicted_demand)}</span>
          <span className="hotspots__sub">{formatDemand(zone.predicted_per_hour)}</span>
        </button>
      ))}
    </div>
  );
}
