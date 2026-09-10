interface Props {
  windowLabel: string;
  maxDemand: number | null;
}

/**
 * Colour ramp for the map. The bands are relative to the busiest zone in the
 * current forecast, which is why the top of the scale is labelled with that
 * zone's predicted figure rather than a fixed number.
 */
export function MapLegend({ windowLabel, maxDemand }: Props) {
  return (
    <div className="legend">
      <div className="legend__title">Predicted demand</div>
      <div className="legend__ramp" />
      <div className="legend__scale">
        <span>0</span>
        <span>{maxDemand == null ? "peak" : `${Math.round(maxDemand)} req`}</span>
      </div>
      <div className="legend__foot">
        Shading is each cell's demand relative to the busiest cell, over the{" "}
        {windowLabel.toLowerCase()}.
      </div>
    </div>
  );
}
