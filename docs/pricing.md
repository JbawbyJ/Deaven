# Pricing comps, range, and history

## UI contract

`price_clusters` returns one `PricedCluster` per `VehicleCluster`. The sort payload is `result`, and `result` has only these fields:

| Field | Type | Meaning |
|---|---|---|
| `deal_score` | float or null | `(estimate.mid - asking) / estimate.mid`. Positive means the asking price is below the estimate. Null when there is no estimate. |
| `deal_rating` | `great`, `good`, `fair`, `high`, or null | `rate_deal` from `backend/pricing/value.py`. `great`, `good`, `fair`, and `high` pass through. `overpriced` maps to `high`. Only `unknown` maps to null. |
| `estimate` | `{low, mid, high}` | All three amounts are in the listing currency. `mid` is the cohort median. `low` and `high` are the 25th and 75th percentiles of the same adjusted comps. Nulls when there is no estimate. |
| `confidence` | float 0–1 | Comp count, spread, and cohort match. This is not the high/medium/low string on `MarketValue`. |
| `comp_count` | int | Comp **clusters** that entered the estimate, after `vehicle_key` collapse. A car listed on BaT and eBay counts as one. |

`cluster_result(subject, comps, prices=None)` is the same object for one subject. Asking price is the cluster's current ask: the latest `asking` observation, otherwise the listing price. No API route and no frontend change. `DealPayload` is unchanged.

`rate_deal` itself still returns `great` / `good` / `fair` / `high` / `overpriced` / `unknown`. Thresholds stay in `value.py`: great ≤ −15% ask versus estimate, good ≤ −5%, fair ≤ +5%, high ≤ +15%, else overpriced. The per-cluster `deal_rating` keeps `great`, `good`, `fair`, and `high` as-is, maps `overpriced` to `high`, and maps only `unknown` to null. Sign is flipped on purpose: #2's internal delta is `(asking - estimate) / estimate` (negative is cheap); `deal_score` is the opposite so a sort descending on `deal_score` puts the cheapest asks first.

This lane is stacked on the comp-based estimate in `docs/pricing/PLAN.md` (`backend/pricing/value.py`). That estimate is unchanged: the median of mileage- and age-adjusted comps in the narrowest cohort, plus the categorical confidence and the deal rating. Call `estimate_value` and `rate_deal` for that behavior.

`assess_price` adds what that baseline left open. It collapses cross-listed rows to one comp, returns a low/high range and a 0–1 confidence score, and reads price history from `PriceObservation` rows.

## Listing adapter

Draft PR #8 (`agent/beebc-grok/listing-model` @ `5bc43fe`, stacked on PR #3) is not merged, and this lane does not edit `shared/`. `backend/pricing/adapter.py` is a thin local mirror of that model's field names:

| Type | Fields pricing reads |
|---|---|
| `NormalizedListing` | `observation_id`, `vin`, `year`, `make`, `model`, `trim`, `mileage`, `price`, `currency`, `location`, `source`, `source_url`, `first_seen`, `last_seen` |
| `ListingLocation` | `label`, `city`, `region`, `country`, `latitude`, `longitude` |
| `PriceObservation` | `listing_id`, `observed_at`, `amount`, `currency`, `kind` (`asking`, `bid`, `sold`, `reserve_not_met`) |
| `VehicleCluster` | `vehicle_key`, `listing_ids`, `match_method` (`vin` or `fuzzy`) |
| `Source` | `code`, `kind`, `name`, `base_url`, `robots_ok`, `tos_reviewed` |
| `Seller` | `name`, `seller_type` |

`ListingData` still flows through `facts_from_listing`. `DealPayload` is not changed.

When `shared.vin.vin_key` and `shared.schemas.market.vehicle_key_for` import, those implementations win. Until PR #8 is on this branch, the adapter uses the same rules locally.

## One comp per vehicle

`vehicle_key` is the identity. It is not a separate fuzzy key invented here.

1. `vin_key(raw: str) -> str | None`. A normalized 17-character VIN, or `None` when the VIN is blank or fails the check digit.
2. Otherwise the sha256 of `year|make|model|trim|mileage band|zip`, matching PR #8:
   - make, model, and trim are case-folded with collapsed whitespace
   - mileage bands are 10,000 miles (`70000-79999`, or `unknown` when mileage is missing)
   - the ZIP is parsed from `location.label` because `ListingLocation` has no zip field

Rows that share a `vehicle_key` become one `CollapsedComp`. `match_method` is `vin` when the key is a VIN, otherwise `fuzzy`. The comp's price is the latest `asking` observation when any exist, otherwise the latest listing price (`last_seen`, then input order).

The BaT and eBay fixtures for the demo M3 share `1HGCM82633A004352`, so they are one comp at the latest ask, $31,200. A missing VIN and the invalid VIN `JH4KA8260MC000000` take the fuzzy hash. The next mileage band does not.

`estimate_value` itself does not collapse. Sourceless `ListingFacts` rows with different VINs stay distinct. Two no-VIN rows with the same year, make, model, trim, mileage band, and label ZIP collapse only when passed through `collapse_clusters` / `assess_price`.

Non-USD rows are omitted. Prices are not converted.

## Distance bands

`ListingLocation` has latitude and longitude and no zip field. After identity collapse, comps are filtered by haversine distance only when **both** the subject and the comp have coordinates:

| Band | Miles | Effect |
|---|---|---|
| metro | 0–50 | kept |
| regional | >50–250 | kept |
| extended | >250–1,000 | kept |
| outside | >1,000 | dropped |

If either side lacks coordinates, the distance filter does not apply and cohort matching falls back to the region logic in `value.py`. There is no zip-to-coordinate lookup. `distance_band` on the assessment is the widest band among the comps that were actually used, or `None` when no pair had coordinates.

The ZIP inside `vehicle_key` is only the identity hash from the label. Two no-VIN cars with the same ZIP and mileage band still collapse even if their coordinates are far apart. Two no-VIN cars 10 miles apart with different ZIPs in the label do not share a `vehicle_key`.

## Range and confidence

The point estimate and the `great` / `good` / `fair` / `high` / `overpriced` rating are still `estimate_value` and `rate_deal`. Thresholds stay in `backend/pricing/value.py`: great ≤ −15%, good ≤ −5%, fair ≤ +5%, high ≤ +15%, else overpriced. No estimate rates `unknown`.

`low` and `high` are the 25th and 75th percentiles of the same mileage- and age-adjusted prices, using linear rank `p * (n - 1)`. One comp has `low == high ==` that adjusted price. No comps leaves both empty.

`confidence` (the string `high` / `medium` / `low` / `insufficient`) is unchanged. `confidence_score` is a separate 0–1 number:

```
count_factor = min(1, comp_count / 8)
spread_factor = max(0, 1 - (IQR / median) / 0.50)
cohort_quality = 1.00  regional trim, year ±1
                 0.80  national trim, year ±1
                 0.55  make + model, year ±2
                 0.35  make + model
quality_term = 0.40 + 0.30 * spread_factor + 0.30 * cohort_quality
confidence_score = round(count_factor * quality_term, 3)
```

Count caps the score, so one tight comp is 0.125 and the score saturates only at 8 comps. A wider IQR lowers it. No comps score 0.

## Price history

`PriceObservation` rows linked by `listing_id` (the normalized listing's `observation_id`) are sorted by `observed_at`. The BaT demo asks $34,800 on 2026-07-01 and $31,200 on 2026-08-01, with a bid in between. Combined with the eBay asks, the asking series is $34,800 → $33,900 → $32,950 → $31,200.

- `drop_count` counts strict decreases between consecutive **asking** points. Bids stay on the series and do not erase an asking drop.
- `first_price` / `last_price` / `change_pct` use the first and last asking amounts.
- `days_on_market` is the whole-day span from the earliest `first_seen` or observation to the latest `last_seen` or observation.

A single listing with one price has no drop. History is not inferred from `listing.price` alone.

## Limitations

- No network, no FX, no scraping. Callers pass USD amounts.
- `estimate_value` does not dedupe. Deduped pricing goes through `assess_price`.
- PR #8 is not on this branch. The local `vehicle_key` is a stand-in and should be deleted once `shared.schemas.market` imports.
- `ListingLocation` has no zip, sold-versus-asking flag on the listing itself, or a price series. History depends on separate `PriceObservation` rows. `kind` distinguishes asking from bid, sold, and reserve-not-met.
- There is no `vin_key` in `shared/vin` on this branch. The adapter prefers that function when it appears.
- Cohort matching is still year / make / model / trim / region. Distance bands do not replace it, and they do nothing without coordinates.
- The subject is removed from its own comps by `vehicle_key` and listing id. A cross-list of the subject is not a comp.
