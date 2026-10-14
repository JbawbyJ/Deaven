import { describe, expect, it } from 'vitest';
import { fixtureListings } from '../fixtures/listings';
import type { ListingObservation } from '../types/listing';
import { filterListings } from './filterListings';
import { queryFromSearchParams } from './searchParams';

const listings = fixtureListings();

const blank = {
  make: '',
  model: '',
  year_min: '',
  year_max: '',
  price_min: '',
  price_max: '',
  mileage_max: '',
  location: '',
  radius: '',
  sort: 'price' as const,
};

describe('filterListings', () => {
  it('filters make, model, year, price, and max mileage', () => {
    const matched = filterListings(listings, {
      ...blank,
      make: 'bm',
      model: 'm3',
      year_min: '2000',
      year_max: '2005',
      price_min: '30000',
      price_max: '32000',
      mileage_max: '70000',
    });

    expect(matched.map((listing) => listing.source)).toEqual(['bat']);
    expect(matched[0].price).toBe(31200);
  });

  it('keeps a listing with unknown mileage when max mileage is set', () => {
    const extra: ListingObservation = {
      ...listings[0],
      observation_id: 'no-miles',
      mileage: null,
      price: 27000,
    };
    const matched = filterListings([extra, ...listings], {
      ...blank,
      make: 'BMW',
      mileage_max: '1000',
    });
    expect(matched.map((listing) => listing.observation_id)).toEqual(['no-miles']);
  });

  it('applies location and radius and drops listings without coordinates', () => {
    const matched = filterListings(listings, {
      ...blank,
      location: 'Austin',
      radius: '50',
      sort: 'distance',
    });
    expect(matched.map((listing) => listing.source).sort()).toEqual(['bat', 'ebay']);
    expect(matched.every((listing) => (listing.distance_miles ?? 99) < 1)).toBe(true);
  });

  it('matches nothing when the location is not in the fixture gazetteer', () => {
    expect(filterListings(listings, { ...blank, location: 'Nowhereville', radius: '500' })).toEqual(
      [],
    );
  });
});

describe('queryFromSearchParams', () => {
  it('reads filter fields from the URL', () => {
    const params = new URLSearchParams(
      'make=BMW&model=M3&year_min=2001&year_max=2006&price_min=10&price_max=40&mileage_max=80000&location=Austin%2C+TX&radius=25&sort=deal',
    );
    expect(queryFromSearchParams(params)).toMatchObject({
      make: 'BMW',
      model: 'M3',
      year_min: '2001',
      year_max: '2006',
      price_min: '10',
      price_max: '40',
      mileage_max: '80000',
      location: 'Austin, TX',
      radius: '25',
      sort: 'deal',
    });
  });
});
