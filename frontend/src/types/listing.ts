/**
 * Local TypeScript mirrors. Not imported from shared/schemas.
 *
 * ListingLocation / NormalizedListing fields: draft PR #3
 * (agent/builder/deaven-ingestion, shared/schemas/listing.py).
 * ListingLocation has no zip field. Latitude and longitude are the map contract.
 *
 * VehicleCluster, PriceObservation, Source, Seller, and vehicle_key:
 * draft PR #8 (agent/beebc-grok/listing-model @ 5bc43fe, shared/schemas/market.py),
 * stacked on #3. vin_key is a normalized VIN, or absent when the VIN is missing
 * or fails the check digit. vehicle_key is that VIN, otherwise the fuzzy hash.
 */

export type SellerType = 'dealer' | 'marketplace' | 'auction';

export type SourceCode =
  | 'bat'
  | 'cab'
  | 'ebay'
  | 'classic_com'
  | 'tcv'
  | 'facebook'
  | 'autotrader'
  | 'hemmings'
  | 'craigslist'
  | 'manual';

/** ListingLocation from PR #3. There is no zip property. */
export type ListingLocation = {
  label?: string | null;
  city?: string | null;
  region?: string | null;
  country?: string | null;
  latitude?: number | null;
  longitude?: number | null;
};

/** Source from PR #8. code reuses DealSource. kind reuses SellerType. */
export type Source = {
  code: SourceCode | string;
  kind: SellerType;
  name: string;
  base_url: string;
  robots_ok: boolean;
  tos_reviewed: boolean;
};

/** Seller from PR #8. seller_type is the #3 channel enum. */
export type Seller = {
  name?: string | null;
  seller_type: SellerType;
};

export type PriceKind = 'asking' | 'bid' | 'sold' | 'reserve_not_met';

/** PriceObservation from PR #8. listing_id is NormalizedListing.observation_id. */
export type PriceObservation = {
  listing_id: string;
  observed_at: string;
  amount: number;
  currency: string;
  kind: PriceKind;
};

export type MatchMethod = 'vin' | 'fuzzy';

/**
 * UI rating from PR #12 @ 9cff34b. overpriced is stored as high.
 * null is only the unknown case, when there is no estimate.
 */
export type DealRating = 'great' | 'good' | 'fair' | 'high';

/** PR #12 Estimate. Each amount is null when there is no estimate. */
export type Estimate = {
  low: number | null;
  mid: number | null;
  high: number | null;
};

/**
 * PR #12 ClusterResult. These five fields only.
 * deal_score = (estimate.mid - asking) / estimate.mid.
 */
export type ClusterResult = {
  deal_score: number | null;
  deal_rating: DealRating | null;
  estimate: Estimate;
  confidence: number;
  comp_count: number;
};

/**
 * VehicleCluster from PR #8. result is PricedCluster.result from PR #12.
 */
export type VehicleCluster = {
  vehicle_key: string;
  listing_ids: string[];
  match_method: MatchMethod;
  result?: ClusterResult | null;
};

/**
 * One source observation shaped like NormalizedListing, plus the #8 identity
 * fields this lane needs in order to group and show a price drop.
 * Pricing lives on VehicleCluster, not on each source observation.
 */
export type ListingObservation = {
  observation_id: string;
  vin: string | null;
  /** Search-lane note. #3 stores an invalid VIN as null, so missing and invalid look alike. */
  vin_note?: 'missing' | 'invalid';
  year: number;
  make: string;
  model: string;
  trim?: string | null;
  mileage?: number | null;
  price: number;
  currency: string;
  location: ListingLocation;
  seller_type: SellerType;
  seller: Seller;
  source: string;
  source_detail: Source;
  source_url: string;
  title?: string | null;
  vehicle_key: string;
  match_method: MatchMethod;
  prices: PriceObservation[];
  distance_miles?: number | null;
};

export type SearchSort = 'price' | 'deal' | 'distance';

export type SearchQuery = {
  make: string;
  model: string;
  year_min: string;
  year_max: string;
  price_min: string;
  price_max: string;
  mileage_max: string;
  location: string;
  radius: string;
  sort: SearchSort;
};

export type ListingSearchResponse = {
  listings: ListingObservation[];
  clusters: VehicleCluster[];
  total: number;
  note: string;
  source: 'api' | 'fixture';
};
