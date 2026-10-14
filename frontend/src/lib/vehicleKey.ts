/**
 * vehicle_key semantics from PR #8 @ 5bc43fe (shared/schemas/market.py).
 * ZIP comes from ListingLocation.label. ListingLocation has no zip field.
 */

import type { ListingLocation, MatchMethod } from '../types/listing';
import { sha256Hex } from './sha256';

const TRANSLIT: Record<string, number> = {
  '0': 0, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
  A: 1, B: 2, C: 3, D: 4, E: 5, F: 6, G: 7, H: 8,
  J: 1, K: 2, L: 3, M: 4, N: 5, P: 7, R: 9,
  S: 2, T: 3, U: 4, V: 5, W: 6, X: 7, Y: 8, Z: 9,
};

const WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2];
const ZIP = /\b(\d{5})(?:-\d{4})?\b/;
const MILEAGE_BAND = 10_000;

export function normalizeVin(value: string): string {
  return value.replace(/[\s-]+/g, '').toUpperCase();
}

/** PR #8 vin_key: normalized VIN, or null when the VIN is missing or invalid. */
export function vinKey(raw: string | null | undefined): string | null {
  if (typeof raw !== 'string' || !raw.trim()) return null;
  const vin = normalizeVin(raw);
  if (vin.length !== 17 || [...vin].some((char) => TRANSLIT[char] == null)) return null;
  const total = [...vin].reduce((sum, char, index) => sum + TRANSLIT[char] * WEIGHTS[index], 0);
  const remainder = total % 11;
  const expected = remainder === 10 ? 'X' : String(remainder);
  if (vin[8] !== expected) return null;
  return vin;
}

/** 10,000-mile bands. Null stays the explicit "unknown" band. */
export function mileageBand(mileage: number | null | undefined): string {
  if (mileage == null || !Number.isFinite(mileage)) return 'unknown';
  const start = Math.floor(mileage / MILEAGE_BAND) * MILEAGE_BAND;
  return `${start}-${start + MILEAGE_BAND - 1}`;
}

/** ZIP digits from the label. ListingLocation has no zip field. */
export function postalCode(location: ListingLocation | null | undefined): string {
  if (!location?.label) return '';
  const match = ZIP.exec(location.label);
  return match ? match[1] : '';
}

function token(value: string | null | undefined): string {
  if (!value) return '';
  return value.trim().toLowerCase().split(/\s+/).join(' ');
}

export function fuzzyVehicleKey(input: {
  year: number;
  make: string;
  model: string;
  trim?: string | null;
  mileage?: number | null;
  location: ListingLocation;
}): string {
  const payload = [
    String(input.year),
    token(input.make),
    token(input.model),
    token(input.trim),
    mileageBand(input.mileage),
    postalCode(input.location),
  ].join('|');
  return sha256Hex(payload);
}

export function vehicleKeyFor(input: {
  vin?: string | null;
  year: number;
  make: string;
  model: string;
  trim?: string | null;
  mileage?: number | null;
  location: ListingLocation;
}): string {
  if (typeof input.vin === 'string' && input.vin.trim()) {
    const key = vinKey(input.vin);
    if (key != null) return key;
  }
  return fuzzyVehicleKey(input);
}

export function matchMethodFor(vehicleKey: string, vin: string | null): MatchMethod {
  if (vin && vin === vehicleKey) return 'vin';
  return 'fuzzy';
}

/** NormalizedListing.observation_id: first 16 hex chars of sha256(source + newline + url). */
export function observationId(source: string, sourceUrl: string): string {
  return sha256Hex(`${source}\n${sourceUrl}`).slice(0, 16);
}
