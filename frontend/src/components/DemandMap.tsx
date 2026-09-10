import { useEffect, useMemo, useRef } from "react";
import { divIcon, type LatLngBoundsExpression, type LatLngTuple } from "leaflet";
import { MapContainer, Marker, Rectangle, TileLayer, Tooltip, useMap } from "react-leaflet";

import type { AppConfig, ZoneDemand } from "../types/demand";
import { LEVEL_COLOR, LEVEL_LABEL, formatDemand } from "../lib/format";

interface Props {
  config: AppConfig;
  zones: ZoneDemand[];
  selectedZoneId: number | null;
  /** Bumped every time the driver explicitly picks an area; drives the fly-to. */
  focusNonce: number;
  onSelectZone: (zoneId: number) => void;
  /** Dim the layer while a new forecast is being fetched. */
  muted: boolean;
  /** Hide predictions entirely (empty and error states). */
  hidden: boolean;
  markerCount?: number;
}

/**
 * Pans the map when the driver explicitly picks an area.
 *
 * Keyed on `nonce` rather than on the selected zone so that generating a new
 * forecast — which also selects the recommended zone — leaves the city-wide
 * view intact instead of zooming in on its own.
 */
function FocusController({ zone, nonce }: { zone: ZoneDemand | null; nonce: number }) {
  const map = useMap();
  // Held in a ref so the fly-to effect can read the current zone without
  // re-running when it changes: a new forecast also selects its top zone, and
  // that must not hijack the map view. This effect is declared first, so the
  // ref is up to date before the one below reads it.
  const target = useRef(zone);
  useEffect(() => {
    target.current = zone;
  }, [zone]);

  useEffect(() => {
    const zoneToFocus = target.current;
    if (!zoneToFocus || nonce === 0) return;
    map.flyTo(
      [zoneToFocus.center.lat, zoneToFocus.center.lng],
      Math.max(map.getZoom(), 14),
      { duration: 0.6 },
    );
  }, [map, nonce]);

  return null;
}

/** Keeps Leaflet's internal size in sync when the panel is first laid out. */
function ResizeHandler() {
  const map = useMap();
  useEffect(() => {
    const timer = window.setTimeout(() => map.invalidateSize(), 120);
    return () => window.clearTimeout(timer);
  }, [map]);
  return null;
}

function markerIcon(zone: ZoneDemand, isTop: boolean) {
  const colour = LEVEL_COLOR[zone.level];
  const ring = isTop
    ? `<span class="map-marker__ring" style="background:${colour}"></span>`
    : "";
  return divIcon({
    className: "zone-label",
    html:
      `<div class="map-marker">${ring}` +
      `<span class="map-marker__dot${isTop ? " map-marker__dot--top" : ""}" ` +
      `style="background:${colour}">${Math.round(zone.predicted_demand)}</span></div>`,
    iconSize: [40, 40],
    iconAnchor: [20, 20],
  });
}

/**
 * The real map: OpenStreetMap tiles through Leaflet, with one rectangle per
 * predicted grid cell. Cell geometry comes from the API (`bounds`), so the
 * squares drawn here are exactly the cells the model predicted for.
 */
export function DemandMap({
  config,
  zones,
  selectedZoneId,
  focusNonce,
  onSelectZone,
  muted,
  hidden,
  markerCount = 5,
}: Props) {
  const center: LatLngTuple = [config.map_center.lat, config.map_center.lng];
  const maxBounds = config.bounds as LatLngBoundsExpression;

  const selectedZone = useMemo(
    () => zones.find((zone) => zone.zone_id === selectedZoneId) ?? null,
    [zones, selectedZoneId],
  );
  const markers = useMemo(() => zones.slice(0, markerCount), [zones, markerCount]);
  const layerOpacity = hidden ? 0 : muted ? 0.4 : 1;

  return (
    <MapContainer
      className="map-panel__canvas"
      center={center}
      zoom={config.map_default_zoom}
      minZoom={10}
      maxBounds={maxBounds}
      maxBoundsViscosity={0.5}
      scrollWheelZoom
      zoomControl
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <ResizeHandler />
      <FocusController zone={selectedZone} nonce={focusNonce} />

      {!hidden && (
        <>
          {zones.map((zone) => {
            const isSelected = zone.zone_id === selectedZoneId;
            return (
              <Rectangle
                key={zone.zone_id}
                bounds={zone.bounds as LatLngBoundsExpression}
                pathOptions={{
                  color: isSelected ? "#101418" : LEVEL_COLOR[zone.level],
                  weight: isSelected ? 2 : 0.5,
                  opacity: isSelected ? 0.9 : 0.35 * layerOpacity,
                  fillColor: LEVEL_COLOR[zone.level],
                  fillOpacity: (0.1 + 0.55 * zone.intensity) * layerOpacity,
                }}
                eventHandlers={{ click: () => onSelectZone(zone.zone_id) }}
              >
                <Tooltip direction="top" offset={[0, -4]} opacity={1}>
                  <strong>{zone.name}</strong>
                  <br />
                  {formatDemand(zone.predicted_demand)} predicted requests
                  <br />
                  {LEVEL_LABEL[zone.level]}
                </Tooltip>
              </Rectangle>
            );
          })}

          {!muted &&
            markers.map((zone, index) => (
              <Marker
                key={`marker-${zone.zone_id}`}
                position={[zone.center.lat, zone.center.lng]}
                icon={markerIcon(zone, index === 0)}
                eventHandlers={{ click: () => onSelectZone(zone.zone_id) }}
              >
                <Tooltip direction="top" offset={[0, -22]} opacity={1}>
                  <strong>{zone.name}</strong>
                  <br />
                  {formatDemand(zone.predicted_demand)} predicted requests
                </Tooltip>
              </Marker>
            ))}
        </>
      )}
    </MapContainer>
  );
}
