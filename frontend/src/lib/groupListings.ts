import type {
  ListingObservation,
  PriceObservation,
  SearchSort,
  VehicleCluster,
} from '../types/listing';
import { clusterResult } from './dealScore';
import { hasCoordinates } from './geo';

export type SourceOffer = {
  observationId: string;
  source: string;
  sourceName: string;
  price: number;
  previousAsking: number | null;
  sourceUrl: string;
};

export type ListingGroup = {
  cluster: VehicleCluster;
  title: string;
  year: number;
  make: string;
  model: string;
  trim: string | null;
  mileage: number | null;
  location: ListingObservation['location'] | null;
  minPrice: number;
  distanceMiles: number | null;
  offers: SourceOffer[];
  observations: ListingObservation[];
};

export function earlierAsking(prices: PriceObservation[]): number | null {
  const asking = prices
    .filter((price) => price.kind === 'asking')
    .slice()
    .sort((a, b) => a.observed_at.localeCompare(b.observed_at));
  if (asking.length < 2) return null;
  const first = asking[0].amount;
  const latest = asking[asking.length - 1].amount;
  return latest < first ? first : null;
}

/** Latest asking observation, otherwise the listing price. PR #12 cluster ask. */
function clusterAsking(observations: ListingObservation[]): number {
  const asking = observations.flatMap((item) =>
    item.prices
      .filter((price) => price.kind === 'asking')
      .map((price) => ({ at: price.observed_at, amount: price.amount })),
  );
  if (asking.length) {
    asking.sort((a, b) => a.at.localeCompare(b.at));
    return asking[asking.length - 1].amount;
  }
  return observations[0]?.price ?? 0;
}

/** Group by VehicleCluster.vehicle_key so one car on several sources shows once. */
export function groupListings(listings: ListingObservation[]): ListingGroup[] {
  const buckets = new Map<string, ListingObservation[]>();
  for (const listing of listings) {
    const bucket = buckets.get(listing.vehicle_key);
    if (bucket) bucket.push(listing);
    else buckets.set(listing.vehicle_key, [listing]);
  }

  return [...buckets.entries()].map(([vehicleKey, observations]) => {
    const first = observations[0];
    const withCoords = observations.find((item) => hasCoordinates(item.location));
    const offers = observations
      .map((item) => ({
        observationId: item.observation_id,
        source: item.source,
        sourceName: item.source_detail.name,
        price: item.price,
        previousAsking: earlierAsking(item.prices),
        sourceUrl: item.source_url,
      }))
      .sort((a, b) => a.price - b.price);
    const distances = observations
      .map((item) => item.distance_miles)
      .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
    const minPrice = Math.min(...observations.map((item) => item.price));
    const cluster: VehicleCluster = {
      vehicle_key: vehicleKey,
      listing_ids: observations.map((item) => item.observation_id),
      match_method: observations.some((item) => item.match_method === 'vin') ? 'vin' : 'fuzzy',
      result: clusterResult(first.model, clusterAsking(observations)),
    };
    const title = [first.year, first.make, first.model, first.trim].filter(Boolean).join(' ');
    return {
      cluster,
      title,
      year: first.year,
      make: first.make,
      model: first.model,
      trim: first.trim ?? null,
      mileage: first.mileage ?? null,
      location: withCoords?.location ?? first.location ?? null,
      minPrice,
      distanceMiles: distances.length ? Math.min(...distances) : null,
      offers,
      observations,
    };
  });
}

function compareAscNullLast(a: number | null, b: number | null): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  return a - b;
}

function compareDescNullLast(a: number | null, b: number | null): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  return b - a;
}

export function sortGroups(groups: ListingGroup[], sort: SearchSort): ListingGroup[] {
  const copy = [...groups];
  copy.sort((a, b) => {
    if (sort === 'distance') {
      return compareAscNullLast(a.distanceMiles, b.distanceMiles) || a.minPrice - b.minPrice;
    }
    if (sort === 'deal') {
      return (
        compareDescNullLast(a.cluster.result?.deal_score ?? null, b.cluster.result?.deal_score ?? null) ||
        a.minPrice - b.minPrice
      );
    }
    return a.minPrice - b.minPrice || a.title.localeCompare(b.title);
  });
  return copy;
}
