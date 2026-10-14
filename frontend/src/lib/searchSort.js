/** Client-side ordering and selection for the listings already returned by search. */

export const SORT_MODES = ['distance', 'price', 'score'];

export const SORT_OPTIONS = [
  { value: 'distance', label: 'Distance' },
  { value: 'price', label: 'Price: low to high' },
  { value: 'score', label: 'Score: high to low' },
];

export function defaultSort(hasCenter) {
  return hasCenter ? 'distance' : 'price';
}

/** Keep an explicit URL sort. Anything else falls back to the center-aware default. */
export function normalizeSort(value, hasCenter) {
  if (SORT_MODES.includes(value)) return value;
  return defaultSort(Boolean(hasCenter));
}

export function listingKey(listing) {
  if (!listing) return null;
  const key = listing.listing_id || listing.deal_id;
  if (key == null || key === '') return null;
  return String(key);
}

function numericOrNull(value) {
  if (value == null || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function identity(listing) {
  return listingKey(listing) ?? '';
}

function compareAscendingNullsLast(left, right) {
  if (left == null && right == null) return 0;
  if (left == null) return 1;
  if (right == null) return -1;
  return left - right;
}

function compareDescendingNullsLast(left, right) {
  if (left == null && right == null) return 0;
  if (left == null) return 1;
  if (right == null) return -1;
  return right - left;
}

function comparePrimary(left, right, mode) {
  if (mode === 'score') {
    return compareDescendingNullsLast(
      numericOrNull(left.deal_score),
      numericOrNull(right.deal_score),
    );
  }
  if (mode === 'distance') {
    return compareAscendingNullsLast(
      numericOrNull(left.distance_miles),
      numericOrNull(right.distance_miles),
    );
  }
  return compareAscendingNullsLast(numericOrNull(left.price), numericOrNull(right.price));
}

function compareIndexed(left, right, mode) {
  const primary = comparePrimary(left.listing, right.listing, mode);
  if (primary !== 0) return primary;
  const price = compareAscendingNullsLast(
    numericOrNull(left.listing.price),
    numericOrNull(right.listing.price),
  );
  if (price !== 0) return price;
  const id = identity(left.listing).localeCompare(identity(right.listing));
  if (id !== 0) return id;
  return left.index - right.index;
}

/** Return a new array. Does not mutate the hits returned by the query. */
export function sortListings(listings, sort, hasCenter = false) {
  const mode = normalizeSort(sort, hasCenter);
  return listings
    .map((listing, index) => ({ listing, index }))
    .sort((left, right) => compareIndexed(left, right, mode))
    .map((item) => item.listing);
}

export function isListingSelected(selectedKey, listing) {
  const key = listingKey(listing);
  return key != null && key === selectedKey;
}

/** Drop a selection that is no longer in the current result set. */
export function pruneSelection(selectedKey, listings) {
  if (!selectedKey) return null;
  const alive = listings.some((listing) => listingKey(listing) === selectedKey);
  return alive ? selectedKey : null;
}

/**
 * Selection shared by the list and the map.
 * `select` replaces the current key. `results` clears it when that hit is gone.
 */
export function reduceSelection(state, event) {
  const current = state?.selectedKey ?? null;
  if (event?.type === 'select') return { selectedKey: listingKey(event.listing) };
  if (event?.type === 'results') {
    return { selectedKey: pruneSelection(current, event.listings ?? []) };
  }
  return { selectedKey: current };
}
