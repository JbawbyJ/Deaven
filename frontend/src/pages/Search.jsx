import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { MapPin } from 'lucide-react';
import ListingMap from '../components/search/ListingMap';
import SearchFilters from '../components/search/SearchFilters';
import ScoreBadge from '../components/ScoreBadge';
import { formatDistance, formatMileage, formatPrice } from '../lib/formatters';
import { getSearchPlaces, searchErrorMessage, searchListings } from '../lib/searchApi';
import {
  SORT_OPTIONS,
  isListingSelected,
  listingKey,
  normalizeSort,
  pruneSelection,
  sortListings,
} from '../lib/searchSort';

const FILTER_KEYS = [
  'location',
  'radius_miles',
  'make',
  'model',
  'year_min',
  'year_max',
  'price_min',
  'price_max',
  'mileage_max',
  'region',
  'zip',
];

function readFilters(params) {
  const blank = [...params.keys()].length === 0;
  return {
    location: blank ? 'Austin, TX' : params.get('location') ?? '',
    radius_miles: params.get('radius_miles') || '1000',
    make: params.get('make') || '',
    model: params.get('model') || '',
    year_min: params.get('year_min') || '',
    year_max: params.get('year_max') || '',
    price_min: params.get('price_min') || '',
    price_max: params.get('price_max') || '',
    mileage_max: params.get('mileage_max') || '',
    region: params.get('region') || '',
    zip: params.get('zip') || '',
  };
}

function explicitSort(params) {
  const value = params.get('sort');
  return SORT_OPTIONS.some((option) => option.value === value) ? value : null;
}

function writeFilters(filters, sort) {
  const next = {};
  FILTER_KEYS.forEach((key) => {
    const value = filters[key];
    if (value === '' || value == null) return;
    next[key] = String(value);
  });
  if (!filters.location) next.location = '';
  if (sort) next.sort = sort;
  return next;
}

export default function Search() {
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => readFilters(params), [params]);
  const sortParam = explicitSort(params);
  const [selectedKey, setSelectedKey] = useState(null);
  const [hoveredKey, setHoveredKey] = useState(null);
  const cardRefs = useRef(new Map());

  const placesQuery = useQuery({
    queryKey: ['search-places'],
    queryFn: getSearchPlaces,
  });

  const searchQuery = useQuery({
    queryKey: ['search', filters],
    queryFn: () => searchListings(filters),
  });

  const listings = searchQuery.data?.listings ?? [];
  const center = searchQuery.data?.center ?? null;
  // Until the response arrives, a location query is treated as centered so the
  // default does not flash from price to distance.
  const hasCenter = searchQuery.isSuccess ? Boolean(center) : Boolean(filters.location.trim());
  const sort = normalizeSort(sortParam, hasCenter);
  const sorted = useMemo(
    () => sortListings(listings, sort, hasCenter),
    [listings, sort, hasCenter],
  );
  const summary = center
    ? `${searchQuery.data?.total ?? 0} listings within ${filters.radius_miles} mi of ${center.label}`
    : `${searchQuery.data?.total ?? 0} listings`;

  useEffect(() => {
    setSelectedKey((current) => pruneSelection(current, sorted));
    setHoveredKey((current) => pruneSelection(current, sorted));
  }, [sorted]);

  useEffect(() => {
    if (!selectedKey) return;
    cardRefs.current.get(selectedKey)?.scrollIntoView({ block: 'nearest' });
  }, [selectedKey]);

  function apply(next) {
    setParams(writeFilters(next, sortParam));
  }

  function updateSort(nextSort) {
    setParams(writeFilters(filters, normalizeSort(nextSort, hasCenter)));
  }

  function selectListing(listing) {
    setSelectedKey(listingKey(listing));
  }

  return (
    <div className="mx-auto max-w-7xl space-y-4 px-4 py-6 lg:px-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Search</h1>
        <p className="max-w-2xl text-sm text-zinc-500">
          Radius search over ingested listings. Select a result to highlight it on the map, then
          open the existing deal page.
        </p>
      </div>

      <SearchFilters
        filters={filters}
        places={placesQuery.data?.places}
        onApply={apply}
        onClear={() =>
          apply({
            ...filters,
            make: '',
            model: '',
            year_min: '',
            year_max: '',
            price_min: '',
            price_max: '',
            mileage_max: '',
            region: '',
            zip: '',
          })
        }
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="font-mono text-xs text-zinc-500">
          {searchQuery.isLoading ? 'Searching…' : searchQuery.isError ? 'Search unavailable' : summary}
        </p>
        <label className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-zinc-500">
          Sort
          <select
            aria-label="Sort results"
            className="input-dark w-auto py-1.5 normal-case tracking-normal"
            value={sort}
            onChange={(event) => updateSort(event.target.value)}
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {searchQuery.isError && (
        <div className="panel px-4 py-8 text-center text-sm text-deaven-fire">
          {searchErrorMessage(searchQuery.error)}
        </div>
      )}

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.9fr)]">
        <div className="space-y-3">
          {!searchQuery.isLoading && !searchQuery.isError && sorted.length === 0 && (
            <div className="panel px-4 py-16 text-center text-sm text-zinc-500">
              No listings in this area. Widen the radius or clear a filter.
            </div>
          )}
          {sorted.map((listing) => {
            const key = listingKey(listing);
            const distance = formatDistance(listing.distance_miles);
            const place = listing.location || listing.region || 'Location unknown';
            const selected = isListingSelected(selectedKey, listing);
            const hovered = hoveredKey === key && !selected;
            return (
              <article
                key={key}
                ref={(node) => {
                  if (!key) return;
                  if (node) cardRefs.current.set(key, node);
                  else cardRefs.current.delete(key);
                }}
                className={[
                  'panel p-4 transition-colors',
                  selected
                    ? 'border-deaven-gold bg-deaven-gold/10'
                    : hovered
                      ? 'border-deaven-gold/40'
                      : '',
                ].join(' ')}
                onMouseEnter={() => setHoveredKey(key)}
                onMouseLeave={() => setHoveredKey((current) => (current === key ? null : current))}
              >
                <button
                  type="button"
                  aria-pressed={selected}
                  onClick={() => selectListing(listing)}
                  className="group block w-full text-left"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <ScoreBadge score={listing.deal_score} tier={listing.deal_tier} />
                        {selected && (
                          <span className="text-[11px] uppercase tracking-wider text-deaven-gold">
                            Selected
                          </span>
                        )}
                      </div>
                      <h2 className="truncate text-base font-semibold text-zinc-100 group-hover:text-deaven-gold">
                        {listing.title}
                      </h2>
                      <p className="mt-1 flex flex-wrap items-center gap-x-3 text-xs text-zinc-500">
                        <span className="inline-flex items-center gap-1">
                          <MapPin className="h-3 w-3" />
                          {place}
                          {listing.zip ? ` · ${listing.zip}` : ''}
                          {distance ? ` · ${distance}` : ''}
                        </span>
                        {listing.mileage != null && <span>{formatMileage(listing.mileage)}</span>}
                        {listing.listing_id && (
                          <span className="font-mono">{listing.listing_id}</span>
                        )}
                        {listing.geo_source === 'fixture_gazetteer' && <span>Fixture pin</span>}
                      </p>
                    </div>
                    <span className="shrink-0 font-mono text-lg font-semibold text-deaven-gold">
                      {formatPrice(listing.price)}
                    </span>
                  </div>
                </button>
                {listing.deal_id && (
                  <div className="mt-3 flex justify-end">
                    <Link
                      to={`/deals/${listing.deal_id}`}
                      className="text-xs font-medium text-deaven-gold hover:underline"
                    >
                      Open deal
                    </Link>
                  </div>
                )}
              </article>
            );
          })}
        </div>

        <ListingMap
          listings={sorted}
          center={center}
          radiusMiles={center ? Number(filters.radius_miles) : null}
          selectedKey={selectedKey}
          hoveredKey={hoveredKey}
          onSelect={selectListing}
          onHover={setHoveredKey}
          className="h-80 lg:sticky lg:top-24 lg:h-[560px]"
        />
      </div>
    </div>
  );
}
