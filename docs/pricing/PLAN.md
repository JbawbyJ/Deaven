# Pricing

Fair price is the median of comparable listings after a mileage and age adjustment. The narrowest cohort with at least 3 comps wins:

1. make + model + trim, year ±1, same region
2. make + model + trim, year ±1
3. make + model, year ±2
4. make + model

Fewer than 3 comps still produces an estimate from the largest narrower set, at low confidence. No comps returns no estimate. Confidence is high only for a regional trim cohort of 5 or more, medium for a smaller regional set or a national trim cohort of 5 or more, otherwise low.

Deal rating compares asking price to that estimate. Thresholds live at the top of `backend/pricing/value.py`: great ≤ −15%, good ≤ −5%, fair ≤ +5%, high ≤ +15%, else overpriced.

Assumptions: caller-supplied USD asking prices, 1.5% per 10k miles, 3% per year, adjustment factor clamped to 0.45–1.80. The subject is dropped from its own comps by listing id and VIN. Region is a state code parsed from `ListingData.location`, or an explicit override. This lane does not scrape.

`agent/builder/deaven-ingestion` was not on the remote. `facts_from_listing` reads `shared.schemas.deal.ListingData` and is the swap point when Builder publishes the schema. `ListingFacts` is not stored.

Next: price history (drops, days on market) and side-by-side comparison, then feed the estimate into valuation only after Builder's schema is in.
