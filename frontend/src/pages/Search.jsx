import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { MapPin } from 'lucide-react';
import ListingMap from '../components/search/ListingMap';
import SearchFilters from '../components/search/SearchFilters';
import ScoreBadge from '../components/ScoreBadge';
import { formatDistance, formatMileage, formatPrice } from '../lib/formatters';
import { getSearchPlaces, searchErrorMessage, searchListings } from '../lib/searchApi';

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
  };
}

function writeFilters(filters) {
  const next = {};
  FILTER_KEYS.forEach((key) => {
    const value = filters[key];
    if (value === '' || value == null) return;
    next[key] = String(value);
  });
  if (!filters.location) next.location = '';
  return next;
}

export default function Search() {
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => readFilters(params), [params]);

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
  const summary = center
    ? `${searchQuery.data?.total ?? 0} listings within ${filters.radius_miles} mi of ${center.label}`
    : `${searchQuery.data?.total ?? 0} listings`;

  function apply(next) {
    setParams(writeFilters(next));
  }

  return (
    <div className="mx-auto max-w-7xl space-y-4 px-4 py-6 lg:px-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Search</h1>
        <p className="max-w-2xl text-sm text-zinc-500">
          Radius search over ingested listings. Open a result for the existing deal page.
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
          })
        }
      />

      <p className="font-mono text-xs text-zinc-500">
        {searchQuery.isLoading ? 'Searching…' : searchQuery.isError ? 'Search unavailable' : summary}
      </p>

      {searchQuery.isError && (
        <div className="panel px-4 py-8 text-center text-sm text-deaven-fire">
          {searchErrorMessage(searchQuery.error)}
        </div>
      )}

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.9fr)]">
        <div className="space-y-3">
          {!searchQuery.isLoading && !searchQuery.isError && listings.length === 0 && (
            <div className="panel px-4 py-16 text-center text-sm text-zinc-500">
              No listings in this area. Widen the radius or clear a filter.
            </div>
          )}
          {listings.map((listing) => {
            const distance = formatDistance(listing.distance_miles);
            return (
              <Link
                key={listing.deal_id}
                to={`/deals/${listing.deal_id}`}
                className="group panel block p-4 transition-colors hover:border-deaven-gold/30"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="mb-2">
                      <ScoreBadge score={listing.deal_score} tier={listing.deal_tier} />
                    </div>
                    <h2 className="truncate text-base font-semibold text-zinc-100 group-hover:text-deaven-gold">
                      {listing.title}
                    </h2>
                    <p className="mt-1 flex flex-wrap items-center gap-x-3 text-xs text-zinc-500">
                      <span className="inline-flex items-center gap-1">
                        <MapPin className="h-3 w-3" />
                        {listing.location || 'Location unknown'}
                        {distance ? ` · ${distance}` : ''}
                      </span>
                      {listing.mileage != null && <span>{formatMileage(listing.mileage)}</span>}
                      {listing.geo_source === 'fixture_gazetteer' && <span>Fixture pin</span>}
                    </p>
                  </div>
                  <span className="shrink-0 font-mono text-lg font-semibold text-deaven-gold">
                    {formatPrice(listing.price)}
                  </span>
                </div>
              </Link>
            );
          })}
        </div>

        <ListingMap
          listings={listings}
          center={center}
          radiusMiles={center ? Number(filters.radius_miles) : null}
          className="h-80 lg:sticky lg:top-24 lg:h-[560px]"
        />
      </div>
    </div>
  );
}
