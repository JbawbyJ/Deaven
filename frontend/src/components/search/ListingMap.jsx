import { Link } from 'react-router-dom';
import { formatPrice } from '../../lib/formatters';
import { isListingSelected, listingKey } from '../../lib/searchSort';

const EMPTY_BOUNDS = { north: 49, south: 25, west: -125, east: -67 };

function computeBounds(listings, center, radiusMiles) {
  const coords = listings
    .filter((item) => item.lat != null && item.lng != null)
    .map((item) => [item.lat, item.lng]);

  if (center && radiusMiles) {
    const dLat = radiusMiles / 69;
    const dLng = radiusMiles / (69 * Math.max(0.2, Math.cos((center.lat * Math.PI) / 180)));
    coords.push([center.lat - dLat, center.lng - dLng], [center.lat + dLat, center.lng + dLng]);
  }

  if (coords.length === 0) return EMPTY_BOUNDS;

  const lats = coords.map((pair) => pair[0]);
  const lngs = coords.map((pair) => pair[1]);
  const north = Math.max(...lats);
  const south = Math.min(...lats);
  const east = Math.max(...lngs);
  const west = Math.min(...lngs);
  const padLat = Math.max((north - south) * 0.12, 0.6);
  const padLng = Math.max((east - west) * 0.12, 0.6);
  return {
    north: north + padLat,
    south: south - padLat,
    east: east + padLng,
    west: west - padLng,
  };
}

function project(lat, lng, bounds) {
  const x = ((lng - bounds.west) / (bounds.east - bounds.west)) * 100;
  const y = ((bounds.north - lat) / (bounds.north - bounds.south)) * 100;
  return { left: `${x}%`, top: `${y}%` };
}

export default function ListingMap({
  listings,
  center,
  radiusMiles,
  selectedKey = null,
  hoveredKey = null,
  onSelect,
  onHover,
  className = '',
}) {
  const mappable = listings.filter((item) => item.lat != null && item.lng != null);
  const bounds = computeBounds(mappable, center, radiusMiles);
  const selected = listings.find((item) => isListingSelected(selectedKey, item)) ?? null;

  let ring = null;
  if (center && radiusMiles) {
    const dLat = radiusMiles / 69;
    const dLng = radiusMiles / (69 * Math.max(0.2, Math.cos((center.lat * Math.PI) / 180)));
    const c = project(center.lat, center.lng, bounds);
    const edge = project(center.lat, center.lng + dLng, bounds);
    const north = project(center.lat + dLat, center.lng, bounds);
    ring = {
      cx: parseFloat(c.left),
      cy: parseFloat(c.top),
      rx: Math.abs(parseFloat(edge.left) - parseFloat(c.left)),
      ry: Math.abs(parseFloat(north.top) - parseFloat(c.top)),
    };
  }

  return (
    <div
      className={[
        'search-map relative overflow-hidden rounded-lg border border-deaven-border bg-[#0c0f14]',
        className,
      ].join(' ')}
    >
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full">
        {[25, 50, 75].map((tick) => (
          <g key={tick}>
            <line x1={tick} y1="0" x2={tick} y2="100" stroke="#1f1f1f" strokeWidth="0.35" />
            <line x1="0" y1={tick} x2="100" y2={tick} stroke="#1f1f1f" strokeWidth="0.35" />
          </g>
        ))}
        {ring && (
          <ellipse
            cx={ring.cx}
            cy={ring.cy}
            rx={ring.rx}
            ry={ring.ry}
            fill="rgba(201,168,76,0.08)"
            stroke="#c9a84c"
            strokeWidth="1"
            vectorEffect="non-scaling-stroke"
          />
        )}
      </svg>

      {mappable.map((listing) => {
        const key = listingKey(listing);
        const point = project(listing.lat, listing.lng, bounds);
        const selectedPin = isListingSelected(selectedKey, listing);
        const hoveredPin = hoveredKey === key && !selectedPin;
        return (
          <button
            key={key}
            type="button"
            title={`${listing.title} · ${formatPrice(listing.price)}`}
            aria-label={`${listing.title}, ${formatPrice(listing.price)}`}
            aria-pressed={selectedPin}
            onClick={() => onSelect?.(listing)}
            onMouseEnter={() => onHover?.(key)}
            onMouseLeave={() => onHover?.(null)}
            className={[
              'absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-black bg-deaven-gold',
              selectedPin
                ? 'z-20 h-5 w-5 shadow-[0_0_0_4px_rgba(201,168,76,0.55)]'
                : hoveredPin
                  ? 'z-10 h-4 w-4 shadow-[0_0_0_3px_rgba(201,168,76,0.45)]'
                  : 'z-10 h-3.5 w-3.5 shadow-[0_0_0_3px_rgba(201,168,76,0.35)]',
            ].join(' ')}
            style={point}
          />
        );
      })}

      {selected && (
        <div className="absolute left-2 right-2 top-2 z-30 flex items-center justify-between gap-2 rounded-md border border-deaven-gold/40 bg-deaven-surface/95 px-3 py-2">
          <p className="truncate text-xs text-zinc-100">{selected.title}</p>
          {selected.deal_id && (
            <Link
              to={`/deals/${selected.deal_id}`}
              className="shrink-0 text-xs font-medium text-deaven-gold hover:underline"
            >
              Open deal
            </Link>
          )}
        </div>
      )}

      <p className="pointer-events-none absolute bottom-2 left-2 right-2 text-[11px] text-zinc-500">
        Simple lat/lng projection.
        {mappable.some((item) => item.geo_source === 'fixture_gazetteer')
          ? ' Pins use the fixture city list until listings store coordinates.'
          : ''}
      </p>
    </div>
  );
}
