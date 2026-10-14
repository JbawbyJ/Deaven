# eBay Browse API

The ingestion adapter (`backend/ingestion/ebay_browse.py`) calls eBay's official Browse API `item_summary/search` at `api.ebay.com`. The Finding API is retired and is not used.

Access is an OAuth client-credentials token from `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET`. The token is cached in memory until it expires. Do not commit either value. `EBAY_APP_ID` was the Finding API key and is deprecated.

The search is limited to the eBay Motors cars and trucks category (`category_ids=6001`, marketplace `EBAY_MOTORS`). The adapter does not scrape eBay HTML and does not impersonate a browser.

Every request sends:

`DeavenBot/0.1 (+https://github.com/JbawbyJ/Deaven; listing-ingestion)`

Before a token request or a search, the adapter reads that host's `robots.txt` and does not call a path that is disallowed, or any API path when robots.txt cannot be read. Requests to the host are spaced by at least one second, or by the robots `Crawl-delay` when that is longer.

eBay's developer agreement is the license for these calls. This note is an engineering rule, not legal advice.

No other source is fetched by this lane.
