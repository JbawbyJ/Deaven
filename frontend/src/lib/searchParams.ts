import type { SearchQuery, SearchSort } from '../types/listing';

const EMPTY: SearchQuery = {
  make: '',
  model: '',
  year_min: '',
  year_max: '',
  price_min: '',
  price_max: '',
  mileage_max: '',
  location: '',
  radius: '',
  sort: 'price',
};

function sortFrom(value: string | null): SearchSort {
  if (value === 'deal' || value === 'distance' || value === 'price') return value;
  return 'price';
}

export function queryFromSearchParams(params: URLSearchParams): SearchQuery {
  return {
    make: params.get('make') ?? '',
    model: params.get('model') ?? '',
    year_min: params.get('year_min') ?? '',
    year_max: params.get('year_max') ?? '',
    price_min: params.get('price_min') ?? '',
    price_max: params.get('price_max') ?? '',
    mileage_max: params.get('mileage_max') ?? '',
    location: params.get('location') ?? '',
    radius: params.get('radius') ?? '',
    sort: sortFrom(params.get('sort')),
  };
}

export function searchParamsFromQuery(query: SearchQuery): URLSearchParams {
  const params = new URLSearchParams();
  const set = (key: keyof SearchQuery, value: string) => {
    const trimmed = value.trim();
    if (trimmed) params.set(key, trimmed);
  };
  set('make', query.make);
  set('model', query.model);
  set('year_min', query.year_min);
  set('year_max', query.year_max);
  set('price_min', query.price_min);
  set('price_max', query.price_max);
  set('mileage_max', query.mileage_max);
  set('location', query.location);
  if (query.location.trim()) {
    params.set('radius', query.radius.trim() || '100');
  }
  if (query.sort !== 'price') params.set('sort', query.sort);
  return params;
}

export function emptyQuery(): SearchQuery {
  return { ...EMPTY };
}

export function parseOptionalNumber(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}
