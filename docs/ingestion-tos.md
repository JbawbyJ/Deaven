# eBay Finding API

The ingestion adapter (`backend/ingestion/ebay_finding.py`) calls eBay's official Finding API at `svcs.ebay.com` with `EBAY_APP_ID`. That API is the allowed access path. The adapter does not scrape eBay HTML and does not impersonate a browser.

Every request sends:

`DeavenBot/0.1 (+https://github.com/JbawbyJ/Deaven; listing-ingestion)`

Before a search, the adapter reads that host's `robots.txt` and does not call the API when the path is disallowed or the file cannot be read. Requests to the host are spaced by at least one second, or by the robots `Crawl-delay` when that is longer.

Put the app id in the environment. Do not commit it. eBay's developer agreement is the license for this call. This note is an engineering rule, not legal advice.

No other source is fetched by this lane.
