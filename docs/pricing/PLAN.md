# Pricing

Fair price is the median of comparable listings after a mileage and age adjustment. The narrowest cohort with at least 3 comps wins:

1. make + model + trim, year ±1, same region
2. make + model + trim, year ±1
3. make + model, year ±2
4. make + model

Fewer than 3 comps still produces an estimate from the largest narrower set, at low confidence. No comps returns no estimate. Confidence is high only for a regional trim cohort of 5 or more, medium for a smaller regional set or a national trim cohort of 5 or more, otherwise low.

Deal rating compares asking price to that estimate. Thresholds live at the top of `backend/pricing/value.py`: great ≤ −15%, good ≤ −5%, fair ≤ +5%, high ≤ +15%, else overpriced.

Assumptions: caller-supplied USD asking prices, 1.5% per 10k miles, 3% per year, adjustment factor clamped to 0.45–1.80. The subject is dropped from its own comps by listing id and VIN. Region is the listing's `region` when that field exists, otherwise the explicit argument. `location` is not parsed. This lane does not scrape.

`facts_from_listing` is still the swap point onto `ListingData`. It uses `region`, `asking_price`, `trim_normalized`, and `listing_id` when those fields are present, and `ListingFacts` is not stored.

Price history is a JSON file next to the local deal store (`price_history.json`). Each row is a listing id, a price, and the time it was seen. The summary is the current and first price, the net drop from the first ask and the most recent decrease (amount and fraction of the earlier price), how many times the price changed, days from the first observation to the last or an as-of time, and a trend of down, up, or flat.

Next: side-by-side comparison, then feed the estimate into valuation once Builder's schema is on main.
