import { describe, expect, it } from 'vitest';
import { fixtureListings } from '../fixtures/listings';
import { sourceFor } from './sources';
import {
  fuzzyVehicleKey,
  mileageBand,
  observationId,
  postalCode,
  vehicleKeyFor,
  vinKey,
} from './vehicleKey';

const RX7_KEY = '11e4d7aba0088b9aab9e9abf2845709881ca5d80d9d2675931ae8b42c1107c89';
const LEGEND_KEY = 'd95f827fb8bb380edd2d63f8eaa9fe4c3a0b7b6700c4a20daa758c5966c2e61b';

describe('vehicle_key', () => {
  it('normalizes the shared BaT and eBay VIN', () => {
    expect(vinKey(' 1hg-cm82633-a004352 ')).toBe('1HGCM82633A004352');
    expect(vinKey('JH4KA8260MC000000')).toBeNull();
    expect(vinKey('')).toBeNull();
    expect(vinKey(null)).toBeNull();

    const [bat, ebay] = fixtureListings();
    expect(bat.vehicle_key).toBe('1HGCM82633A004352');
    expect(ebay.vehicle_key).toBe(bat.vehicle_key);
    expect(bat.vin).toBe(ebay.vin);
    expect(bat.match_method).toBe('vin');
    expect(bat.observation_id).toBe('bd8f0e137da82645');
    expect(ebay.observation_id).toBe('873b796649b684da');
    expect(observationId('bat', bat.source_url)).toBe(bat.observation_id);
    expect(bat.prices.every((price) => price.listing_id === bat.observation_id)).toBe(true);
    expect(bat.source_detail).toEqual(sourceFor('bat'));
    expect(bat.source_detail.robots_ok).toBe(false);
    expect(bat.seller.seller_type).toBe('auction');
    expect(ebay.seller.seller_type).toBe('marketplace');
  });

  it('records the asking price drop on both sources', () => {
    const [bat, ebay] = fixtureListings();
    const batAsking = bat.prices.filter((price) => price.kind === 'asking');
    const ebayAsking = ebay.prices.filter((price) => price.kind === 'asking');
    expect(batAsking.at(-1)?.amount).toBeLessThan(batAsking[0].amount);
    expect(batAsking.at(-1)?.amount).toBe(bat.price);
    expect(ebayAsking.at(-1)?.amount).toBeLessThan(ebayAsking[0].amount);
    expect(ebayAsking.at(-1)?.amount).toBe(ebay.price);
  });

  it('hashes a missing VIN from year, make, model, trim, mileage band, and label ZIP', () => {
    const rx7 = fixtureListings().find((listing) => listing.model === 'RX-7');
    expect(rx7?.vin).toBeNull();
    expect(rx7?.vin_note).toBe('missing');
    expect(rx7?.vehicle_key).toBe(RX7_KEY);
    expect(rx7?.match_method).toBe('fuzzy');
    expect(rx7?.location).not.toHaveProperty('zip');
    expect(postalCode(rx7?.location)).toBe('97202');
    expect(mileageBand(70000)).toBe('70000-79999');
    expect(mileageBand(79999)).toBe('70000-79999');
    expect(mileageBand(80000)).toBe('80000-89999');
    expect(mileageBand(null)).toBe('unknown');
    expect(
      fuzzyVehicleKey({
        year: 1993,
        make: 'MAZDA',
        model: 'RX-7',
        trim: ' touring ',
        mileage: 79999,
        location: { label: 'Portland, OR 97202', city: 'Portland', region: 'OR' },
      }),
    ).toBe(RX7_KEY);
  });

  it('sends an invalid VIN down the fuzzy path', () => {
    const legend = fixtureListings().find((listing) => listing.model === 'Legend');
    expect(legend?.vin).toBeNull();
    expect(legend?.vin_note).toBe('invalid');
    expect(legend?.vehicle_key).toBe(LEGEND_KEY);
    expect(legend?.location.latitude).toBeUndefined();
    expect(legend?.location.longitude).toBeUndefined();
    expect(
      vehicleKeyFor({
        vin: 'JH4KA8260MC000000',
        year: 1991,
        make: 'Acura',
        model: 'Legend',
        trim: 'L',
        mileage: 142000,
        location: { label: 'Denver, CO 80202', city: 'Denver', region: 'CO', country: 'US' },
      }),
    ).toBe(LEGEND_KEY);
  });
});
