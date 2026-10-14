import assert from 'node:assert/strict';
import test from 'node:test';
import {
  defaultSort,
  isListingSelected,
  listingKey,
  normalizeSort,
  reduceSelection,
  sortListings,
} from './searchSort.js';

function hit(overrides) {
  return {
    listing_id: null,
    deal_id: 'deal',
    title: 'Car',
    price: 10000,
    distance_miles: 10,
    deal_score: 50,
    ...overrides,
  };
}

test('distance is the default only when a center exists', () => {
  assert.equal(defaultSort(true), 'distance');
  assert.equal(defaultSort(false), 'price');
  assert.equal(normalizeSort(null, true), 'distance');
  assert.equal(normalizeSort('', false), 'price');
  assert.equal(normalizeSort('nope', true), 'distance');
  assert.equal(normalizeSort('score', false), 'score');
});

test('distance sort is closest first and leaves unknown distances last', () => {
  const sorted = sortListings(
    [
      hit({ deal_id: 'far', distance_miles: 80, price: 1000 }),
      hit({ deal_id: 'unknown', distance_miles: null, price: 1 }),
      hit({ deal_id: 'near', distance_miles: 4, price: 9000 }),
    ],
    'distance',
    true,
  );
  assert.deepEqual(
    sorted.map((item) => item.deal_id),
    ['near', 'far', 'unknown'],
  );
});

test('price sort is low to high, with null prices last', () => {
  const sorted = sortListings(
    [
      hit({ deal_id: 'mid', price: 12000 }),
      hit({ deal_id: 'missing', price: null }),
      hit({ deal_id: 'low', price: 4000 }),
    ],
    'price',
    true,
  );
  assert.deepEqual(
    sorted.map((item) => item.deal_id),
    ['low', 'mid', 'missing'],
  );
});

test('score sort is high to low and puts null scores last', () => {
  const sorted = sortListings(
    [
      hit({ deal_id: 'low-score', deal_score: 10, price: 1000 }),
      hit({ deal_id: 'unscored', deal_score: null, price: 1 }),
      hit({ deal_id: 'high-score', deal_score: 90, price: 50000 }),
      hit({ deal_id: 'blank', deal_score: undefined, price: 2 }),
    ],
    'score',
    true,
  );
  assert.deepEqual(
    sorted.map((item) => item.deal_id),
    ['high-score', 'low-score', 'unscored', 'blank'],
  );
});

test('equal primary keys break ties by price, then listing identity', () => {
  const sorted = sortListings(
    [
      hit({ listing_id: 'b', deal_id: '2', distance_miles: 12, price: 8000, deal_score: 70 }),
      hit({ listing_id: 'a', deal_id: '1', distance_miles: 12, price: 8000, deal_score: 70 }),
      hit({ listing_id: 'c', deal_id: '3', distance_miles: 12, price: 3000, deal_score: 70 }),
    ],
    'distance',
    true,
  );
  assert.deepEqual(
    sorted.map((item) => item.listing_id),
    ['c', 'a', 'b'],
  );
});

test('sort does not mutate the returned hits', () => {
  const listings = [hit({ deal_id: 'b', price: 2 }), hit({ deal_id: 'a', price: 1 })];
  const sorted = sortListings(listings, 'price', false);
  assert.deepEqual(
    listings.map((item) => item.deal_id),
    ['b', 'a'],
  );
  assert.notEqual(sorted, listings);
  assert.deepEqual(
    sorted.map((item) => item.deal_id),
    ['a', 'b'],
  );
});

test('list and map share one selection key', () => {
  const listing = hit({ listing_id: 'src:1', deal_id: 'deal-9' });
  const fallback = hit({ listing_id: null, deal_id: 'deal-9' });
  assert.equal(listingKey(listing), 'src:1');
  assert.equal(listingKey(fallback), 'deal-9');

  const selected = reduceSelection({ selectedKey: null }, { type: 'select', listing });
  assert.equal(selected.selectedKey, 'src:1');
  assert.equal(isListingSelected(selected.selectedKey, listing), true);
  assert.equal(isListingSelected(selected.selectedKey, fallback), false);

  const replaced = reduceSelection(selected, { type: 'select', listing: fallback });
  assert.equal(replaced.selectedKey, 'deal-9');
  assert.equal(isListingSelected(replaced.selectedKey, listing), false);
  assert.equal(isListingSelected(replaced.selectedKey, fallback), true);
});

test('a new result set keeps the selection only while that hit is present', () => {
  const kept = hit({ deal_id: 'keep' });
  const gone = hit({ deal_id: 'gone' });
  const selected = reduceSelection({ selectedKey: null }, { type: 'select', listing: gone });
  const stillThere = reduceSelection(selected, { type: 'results', listings: [kept, gone] });
  assert.equal(stillThere.selectedKey, 'gone');
  const cleared = reduceSelection(stillThere, { type: 'results', listings: [kept] });
  assert.equal(cleared.selectedKey, null);
  assert.equal(isListingSelected(cleared.selectedKey, kept), false);
});
