import type { ListingObservation, SearchQuery } from '../types/listing';
import { distanceMiles, resolvePlace } from './geo';
import { parseOptionalNumber } from './searchParams';

function includes(value: string, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return value.toLowerCase().includes(needle);
}

/** Client-side filter used when the search API is unavailable. */
export function filterListings(
  listings: ListingObservation[],
  query: SearchQuery,
): ListingObservation[] {
  const place = query.location.trim() ? resolvePlace(query.location) : null;
  if (query.location.trim() && !place) return [];
  const radius = place ? (parseOptionalNumber(query.radius) ?? 100) : null;
  const yearMin = parseOptionalNumber(query.year_min);
  const yearMax = parseOptionalNumber(query.year_max);
  const priceMin = parseOptionalNumber(query.price_min);
  const priceMax = parseOptionalNumber(query.price_max);
  const mileageMax = parseOptionalNumber(query.mileage_max);

  return listings.flatMap((listing) => {
    if (!includes(listing.make, query.make) || !includes(listing.model, query.model)) return [];
    if (yearMin != null && listing.year < yearMin) return [];
    if (yearMax != null && listing.year > yearMax) return [];
    if (priceMin != null && listing.price < priceMin) return [];
    if (priceMax != null && listing.price > priceMax) return [];
    if (mileageMax != null && listing.mileage != null && listing.mileage > mileageMax) return [];

    if (!place || radius == null) {
      return [{ ...listing, distance_miles: null }];
    }
    const latitude = listing.location.latitude;
    const longitude = listing.location.longitude;
    if (latitude == null || longitude == null) return [];
    const distance = distanceMiles(place.latitude, place.longitude, latitude, longitude);
    if (distance > radius) return [];
    return [{ ...listing, distance_miles: distance }];
  });
}
