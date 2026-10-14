import { fixtureListings } from '../fixtures/listings';
import type { ListingSearchResponse, SearchQuery } from '../types/listing';
import { filterListings } from './filterListings';
import { groupListings } from './groupListings';
import { searchParamsFromQuery } from './searchParams';

export const FIXTURE_NOTE =
  'Local fixtures shaped like PR #8 @ 5bc43fe (VehicleCluster, PriceObservation, Source, Seller, vehicle_key), stacked on PR #3 ListingLocation lat/lon. ListingLocation has no zip field. Cluster result follows PR #12 @ 9cff34b: deal_score, deal_rating, estimate, confidence, and comp_count. deal_rating is great, good, fair, or high; overpriced maps to high; null only when there is no estimate.';

export async function searchListings(query: SearchQuery): Promise<ListingSearchResponse> {
  const base = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');
  const params = searchParamsFromQuery(query);
  try {
    const response = await fetch(`${base}/api/listings/search?${params.toString()}`);
    if (!response.ok) throw new Error(`search ${response.status}`);
    const body = await response.json();
    const listings = Array.isArray(body.listings) ? body.listings : [];
    return {
      listings,
      clusters: Array.isArray(body.clusters) ? body.clusters : groupListings(listings).map((group) => group.cluster),
      total: typeof body.total === 'number' ? body.total : listings.length,
      note: typeof body.note === 'string' ? body.note : FIXTURE_NOTE,
      source: 'api',
    };
  } catch {
    const listings = filterListings(fixtureListings(), query);
    return {
      listings,
      clusters: groupListings(listings).map((group) => group.cluster),
      total: listings.length,
      note: FIXTURE_NOTE,
      source: 'fixture',
    };
  }
}
