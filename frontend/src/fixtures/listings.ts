/**
 * Search fixtures shaped like PR #8 @ 5bc43fe shared/fixtures/listings:
 * bat_e46 + ebay_e46 (same car, both with a price drop), no_vin, invalid_vin.
 * The invalid-VIN record is completed the way that PR's test builds a listing
 * (price 18000, craigslist) because the JSON file itself is only identity fields.
 * Provenance hashes stay on #3/#8 and are not copied here.
 */

import type { ListingObservation, PriceKind, PriceObservation, SellerType } from '../types/listing';
import { sourceFor } from '../lib/sources';
import { matchMethodFor, observationId, vehicleKeyFor, vinKey } from '../lib/vehicleKey';
import type { SourceCode } from '../types/listing';

type RawPrice = {
  observed_at: string;
  amount: number;
  currency: string;
  kind: PriceKind;
};

type RawListing = {
  vin?: string | null;
  vin_note?: 'missing' | 'invalid';
  year: number;
  make: string;
  model: string;
  trim?: string | null;
  mileage?: number | null;
  price: number;
  currency: string;
  location: ListingObservation['location'];
  seller_type: SellerType;
  source: SourceCode;
  source_url: string;
  title: string;
  prices?: RawPrice[];
};

const RAW: RawListing[] = [
  {
    vin: '1HGCM82633A004352',
    year: 2003,
    make: 'BMW',
    model: 'M3',
    trim: 'Coupe',
    mileage: 62140,
    price: 31200,
    currency: 'USD',
    location: {
      label: 'Austin, TX 78701',
      city: 'Austin',
      region: 'TX',
      country: 'US',
      latitude: 30.2672,
      longitude: -97.7431,
    },
    seller_type: 'auction',
    source: 'bat',
    source_url: 'https://bringatrailer.com/listing/deaven-demo-2003-bmw-m3',
    title: '2003 BMW M3 Coupe',
    prices: [
      { observed_at: '2026-07-01T00:00:00Z', amount: 34800, currency: 'USD', kind: 'asking' },
      { observed_at: '2026-07-15T18:30:00Z', amount: 30500, currency: 'USD', kind: 'bid' },
      { observed_at: '2026-08-01T00:00:00Z', amount: 31200, currency: 'USD', kind: 'asking' },
    ],
  },
  {
    vin: '1hg-cm82633-a004352',
    year: 2003,
    make: 'BMW',
    model: 'M3',
    trim: 'Coupe',
    mileage: 62210,
    price: 32950,
    currency: 'USD',
    location: {
      label: 'Austin, TX 78701',
      city: 'Austin',
      region: 'TX',
      country: 'US',
      latitude: 30.2672,
      longitude: -97.7431,
    },
    seller_type: 'marketplace',
    source: 'ebay',
    source_url: 'https://www.ebay.com/itm/deaven-demo-2003-bmw-m3',
    title: '2003 BMW M3 Coupe',
    prices: [
      { observed_at: '2026-07-18T00:00:00Z', amount: 33900, currency: 'USD', kind: 'asking' },
      { observed_at: '2026-07-20T00:00:00Z', amount: 32950, currency: 'USD', kind: 'asking' },
    ],
  },
  {
    vin: null,
    vin_note: 'missing',
    year: 1993,
    make: 'Mazda',
    model: 'RX-7',
    trim: 'Touring',
    mileage: 78400,
    price: 32500,
    currency: 'USD',
    location: {
      label: 'Portland, OR 97202',
      city: 'Portland',
      region: 'OR',
      country: 'US',
    },
    seller_type: 'marketplace',
    source: 'hemmings',
    source_url: 'https://www.hemmings.com/listing/deaven-demo-1993-mazda-rx7',
    title: '1993 Mazda RX-7 Touring',
  },
  {
    vin: 'JH4KA8260MC000000',
    vin_note: 'invalid',
    year: 1991,
    make: 'Acura',
    model: 'Legend',
    trim: 'L',
    mileage: 142000,
    price: 18000,
    currency: 'USD',
    location: {
      label: 'Denver, CO 80202',
      city: 'Denver',
      region: 'CO',
      country: 'US',
    },
    seller_type: 'marketplace',
    source: 'craigslist',
    source_url: 'https://example.com/listings/invalid-vin',
    title: '1991 Acura Legend L',
  },
];

function toObservation(raw: RawListing): ListingObservation {
  const id = observationId(raw.source, raw.source_url);
  const normalizedVin = vinKey(raw.vin);
  const vehicleKey = vehicleKeyFor({
    vin: raw.vin,
    year: raw.year,
    make: raw.make,
    model: raw.model,
    trim: raw.trim,
    mileage: raw.mileage,
    location: raw.location,
  });
  const prices: PriceObservation[] = (raw.prices ?? []).map((price) => ({
    listing_id: id,
    observed_at: price.observed_at,
    amount: price.amount,
    currency: price.currency,
    kind: price.kind,
  }));
  const detail = sourceFor(raw.source);
  return {
    observation_id: id,
    vin: normalizedVin,
    vin_note: raw.vin_note,
    year: raw.year,
    make: raw.make,
    model: raw.model,
    trim: raw.trim ?? null,
    mileage: raw.mileage ?? null,
    price: raw.price,
    currency: raw.currency,
    location: raw.location,
    seller_type: raw.seller_type,
    seller: { name: null, seller_type: raw.seller_type },
    source: raw.source,
    source_detail: detail,
    source_url: raw.source_url,
    title: raw.title,
    vehicle_key: vehicleKey,
    match_method: matchMethodFor(vehicleKey, normalizedVin),
    prices,
    distance_miles: null,
  };
}

export function fixtureListings(): ListingObservation[] {
  return RAW.map(toObservation);
}
