import type { ListingLocation } from '../types/listing';

const EARTH_MILES = 3958.7613;

export function hasCoordinates(location?: ListingLocation | null): boolean {
  const latitude = location?.latitude;
  const longitude = location?.longitude;
  return (
    typeof latitude === 'number' &&
    Number.isFinite(latitude) &&
    typeof longitude === 'number' &&
    Number.isFinite(longitude)
  );
}

export function distanceMiles(
  latitudeA: number,
  longitudeA: number,
  latitudeB: number,
  longitudeB: number,
): number {
  const toRad = (degrees: number) => (degrees * Math.PI) / 180;
  const dLat = toRad(latitudeB - latitudeA);
  const dLon = toRad(longitudeB - longitudeA);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(latitudeA)) * Math.cos(toRad(latitudeB)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_MILES * Math.asin(Math.min(1, Math.sqrt(a)));
}

export type MapCenter = { latitude: number; longitude: number; label: string };

const GAZETTEER: MapCenter[] = [
  { label: 'Austin, TX', latitude: 30.2672, longitude: -97.7431 },
  { label: 'Portland, OR', latitude: 45.5152, longitude: -122.6784 },
  { label: 'Denver, CO', latitude: 39.7392, longitude: -104.9903 },
  { label: 'Los Angeles, CA', latitude: 34.0522, longitude: -118.2437 },
];

/** Fixture places for the location box. Not a live geocoder. */
export function resolvePlace(input: string): MapCenter | null {
  const trimmed = input.trim();
  if (!trimmed) return null;
  const pair = trimmed.match(/^(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)$/);
  if (pair) {
    const latitude = Number(pair[1]);
    const longitude = Number(pair[2]);
    if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) return null;
    return { latitude, longitude, label: trimmed };
  }
  const needle = trimmed.toLowerCase();
  return (
    GAZETTEER.find((place) => {
      const full = place.label.toLowerCase();
      const city = full.split(',')[0].trim();
      return needle === full || needle === city;
    }) ?? null
  );
}
