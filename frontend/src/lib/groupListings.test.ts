import { describe, expect, it } from 'vitest';
import { fixtureListings } from '../fixtures/listings';
import type { ListingObservation } from '../types/listing';
import { earlierAsking, groupListings, sortGroups } from './groupListings';

describe('groupListings', () => {
  it('groups the BaT and eBay M3 by vehicle_key and keeps each price drop', () => {
    const groups = groupListings(fixtureListings());
    const m3 = groups.find((group) => group.model === 'M3');
    expect(m3?.cluster.vehicle_key).toBe('1HGCM82633A004352');
    expect(m3?.cluster.match_method).toBe('vin');
    expect(m3?.cluster.listing_ids).toEqual(['bd8f0e137da82645', '873b796649b684da']);
    expect(m3?.offers.map((offer) => offer.source).sort()).toEqual(['bat', 'ebay']);
    expect(m3?.offers.map((offer) => offer.price).sort((a, b) => a - b)).toEqual([31200, 32950]);
    expect(m3?.offers.find((offer) => offer.source === 'bat')?.previousAsking).toBe(34800);
    expect(m3?.offers.find((offer) => offer.source === 'ebay')?.previousAsking).toBe(33900);
    expect(groups.filter((group) => group.model === 'M3')).toHaveLength(1);
    expect(groups.map((group) => group.model).sort()).toEqual(['Legend', 'M3', 'RX-7']);
  });

  it('does not merge the no-VIN and invalid-VIN cars', () => {
    const groups = groupListings(fixtureListings());
    const fuzzy = groups.filter((group) => group.cluster.match_method === 'fuzzy');
    expect(fuzzy).toHaveLength(2);
    expect(new Set(fuzzy.map((group) => group.cluster.vehicle_key)).size).toBe(2);
  });

  it('uses coordinates from any source in the cluster', () => {
    const [bat, ebay] = fixtureListings();
    const withoutCoords: ListingObservation = {
      ...bat,
      location: { label: 'Austin, TX 78701', city: 'Austin', region: 'TX', country: 'US' },
    };
    const groups = groupListings([withoutCoords, ebay]);
    expect(groups).toHaveLength(1);
    expect(groups[0].location?.latitude).toBe(30.2672);
    expect(groups[0].location?.longitude).toBe(-97.7431);
  });

  it('sorts by price, and leaves listings without a distance last', () => {
    const listings = fixtureListings().map((listing) => ({
      ...listing,
      distance_miles: listing.location.latitude == null ? null : 4,
    }));
    const byPrice = sortGroups(groupListings(fixtureListings()), 'price');
    expect(byPrice.map((group) => group.model)).toEqual(['Legend', 'M3', 'RX-7']);
    const byDistance = sortGroups(groupListings(listings), 'distance');
    expect(byDistance[0].model).toBe('M3');
    expect(byDistance.at(-1)?.distanceMiles).toBeNull();
    expect(earlierAsking([])).toBeNull();
  });

  it('treats deal sort as price because deal_score is not on the listing model', () => {
    const sorted = sortGroups(groupListings(fixtureListings()), 'deal');
    expect(sorted.map((group) => group.model)).toEqual(['Legend', 'M3', 'RX-7']);
  });
});
