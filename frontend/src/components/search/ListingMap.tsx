import { useEffect, useMemo, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { getMapConfig, tileLayerOptions } from '../../config/mapConfig';
import { hasCoordinates } from '../../lib/geo';
import type { ListingGroup } from '../../lib/groupListings';

type Props = {
  groups: ListingGroup[];
  selectedKey: string | null;
  onSelect: (vehicleKey: string) => void;
};

export default function ListingMap({ groups, selectedKey, onSelect }: Props) {
  const config = getMapConfig();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<L.LayerGroup | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  const plottable = useMemo(
    () => groups.filter((group) => hasCoordinates(group.location)),
    [groups],
  );
  const skipped = groups.filter((group) => !hasCoordinates(group.location));
  const plottedKey = plottable.map((group) => group.cluster.vehicle_key).join('|');

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return undefined;
    let map: L.Map | null = null;
    try {
      map = L.map(element, {
        zoomControl: true,
        attributionControl: false,
        scrollWheelZoom: true,
      }).setView([39.8, -98.6], 4);
      L.tileLayer(
        config.tileUrl,
        tileLayerOptions(config.attribution, config.attributionUrl),
      ).addTo(map);
    } catch {
      return undefined;
    }
    mapRef.current = map;
    return () => {
      markersRef.current = null;
      map?.remove();
      mapRef.current = null;
    };
  }, [config.attribution, config.attributionUrl, config.tileUrl]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return undefined;
    markersRef.current?.remove();
    const layer = L.layerGroup().addTo(map);
    markersRef.current = layer;
    const bounds = L.latLngBounds([]);
    plottable.forEach((group) => {
      const latitude = group.location?.latitude;
      const longitude = group.location?.longitude;
      if (latitude == null || longitude == null) return;
      const selected = group.cluster.vehicle_key === selectedKey;
      const marker = L.marker([latitude, longitude], {
        title: group.title,
        icon: L.divIcon({
          className: selected
            ? 'leaflet-div-icon listing-marker is-selected'
            : 'leaflet-div-icon listing-marker',
          iconSize: [16, 16],
          iconAnchor: [8, 8],
        }),
      });
      marker.on('click', () => onSelectRef.current(group.cluster.vehicle_key));
      marker.addTo(layer);
      bounds.extend([latitude, longitude]);
    });
    if (plottable.length === 1) {
      const latitude = plottable[0].location?.latitude;
      const longitude = plottable[0].location?.longitude;
      if (latitude != null && longitude != null) map.setView([latitude, longitude], 8);
    } else if (plottable.length > 1) {
      map.fitBounds(bounds, { padding: [24, 24], maxZoom: 8, animate: false });
    }
    return undefined;
  }, [plottedKey, plottable, selectedKey]);

  const plottedNoun = plottable.length === 1 ? 'listing' : 'listings';
  const skippedNoun = skipped.length === 1 ? 'listing' : 'listings';

  return (
    <section
      data-testid="listing-map"
      role="region"
      aria-label={`Map showing ${plottable.length} ${plottedNoun}`}
      className="panel relative overflow-hidden"
    >
      <div ref={containerRef} className="listing-map-canvas" />
      <a
        className="absolute bottom-2 right-2 z-[2] rounded bg-deaven-bg/90 px-2 py-1 text-xs text-zinc-200 underline-offset-2 hover:underline"
        href={config.attributionUrl}
        target="_blank"
        rel="noreferrer"
      >
        {config.attribution}
      </a>
      {skipped.length > 0 && (
        <p role="status" className="border-t border-deaven-border px-3 py-2 text-xs text-zinc-500">
          {skipped.length} {skippedNoun} not shown on the map (no coordinates):{' '}
          {skipped.map((group) => group.title).join(', ')}
        </p>
      )}
    </section>
  );
}
