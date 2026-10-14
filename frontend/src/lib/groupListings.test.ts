import { describe, expect, it } from 'vitest';
import { fixtureListings } from '../fixtures/listings';
import type { ListingGroup } from './groupListings';
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
    expect(groups.map((group) => group.model).sort()).toEqual(['Legend', 'M3', 'RX-7', 'S2000']);
  });

  it('does not merge the no-VIN and invalid-VIN cars', () => {
    const groups = groupListings(fixtureListings());
    const fuzzy = groups.filter((group) => group.cluster.match_method === 'fuzzy');
    expect(fuzzy).toHaveLength(3);
    expect(new Set(fuzzy.map((group) => group.cluster.vehicle_key)).size).toBe(3);
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
    expect(byPrice.map((group) => group.model)).toEqual(['Legend', 'S2000', 'M3', 'RX-7']);
    const byDistance = sortGroups(groupListings(listings), 'distance');
    expect(byDistance[0].model).toBe('M3');
    expect(byDistance.at(-1)?.distanceMiles).toBeNull();
    expect(earlierAsking([])).toBeNull();
  });

  it('sorts deal_score descending and leaves a missing estimate last', () => {
    const sorted = sortGroups(groupListings(fixtureListings()), 'deal');
    expect(sorted.map((group) => group.model)).toEqual(['M3', 'RX-7', 'S2000', 'Legend']);
    expect(sorted[0].cluster.result?.deal_score).toBeCloseTo(0.22);
    expect(sorted[0].cluster.result?.deal_rating).toBe('great');
    expect(sorted[0].cluster.result?.estimate).toEqual({ low: 36000, mid: 40000, high: 46000 });
    expect(sorted[1].cluster.result?.deal_rating).toBe('good');
    expect(sorted[1].cluster.result?.deal_score).toBeLessThan(sorted[0].cluster.result?.deal_score ?? 0);
    const high = sorted.find((group) => group.model === 'S2000');
    expect(high?.cluster.result?.deal_rating).toBe('high');
    expect(high?.cluster.result?.deal_score).toBeLessThan(-0.05);
    expect(sorted.at(-1)?.cluster.result?.deal_score).toBeNull();
    expect(sorted.at(-1)?.cluster.result?.deal_rating).toBeNull();
    expect(sorted.at(-1)?.cluster.result?.estimate).toEqual({ low: null, mid: null, high: null });
    expect(sorted.at(-1)?.cluster.result?.confidence).toBe(0);
    expect(sorted.at(-1)?.cluster.result?.comp_count).toBe(0);
  });

  it('puts a null deal_score after a negative score', () => {
    const base = groupListings(fixtureListings())[0];
    const row = (
      model: string,
      dealScore: number | null,
      minPrice: number,
    ): ListingGroup => ({
      ...base,
      model,
      title: model,
      minPrice,
      cluster: {
        ...base.cluster,
        vehicle_key: model,
        result: {
          deal_score: dealScore,
          deal_rating: dealScore == null ? null : 'fair',
          estimate: dealScore == null ? { low: null, mid: null, high: null } : { low: 1, mid: 1, high: 1 },
          confidence: dealScore == null ? 0 : 0.5,
          comp_count: dealScore == null ? 0 : 1,
        },
      },
    });
    const sorted = sortGroups(
      [row('Null', null, 1), row('Negative', -0.2, 1), row('High', 0.4, 99999), row('Mid', 0.02, 1)],
      'deal',
    );
    expect(sorted.map((group) => group.model)).toEqual(['High', 'Mid', 'Negative', 'Null']);
  });
});
