# Deaven frontend

React, Vite, and Tailwind. The deal feed talks to the FastAPI app. Search and the map are a separate lane.

## Run

```bash
cd frontend
cp .env.example .env.local   # optional
npm install
npm run dev
```

Open http://localhost:5173. Search is at `/search`.

```bash
npm test
npm run build
```

## Environment

`.env.example` lists every variable. None of them are secrets.

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000` | API origin. Search calls `{VITE_API_URL}/api/listings/search`. |
| `VITE_MAP_TILE_URL` | `https://tile.openstreetmap.org/{z}/{x}/{y}.png` | Leaflet tile template. Swap the provider before ship. |
| `VITE_MAP_ATTRIBUTION` | `© OpenStreetMap contributors` | Visible credit. The map links it to https://www.openstreetmap.org/copyright. |

If the search API is down, the page uses the local fixtures.

## Map tiles

The defaults follow the [OpenStreetMap tile usage policy](https://operations.osmfoundation.org/policies/tiles/):

- The credit `© OpenStreetMap contributors` is visible on the map and links to the copyright page.
- Tiles load for the current view only. The tile layer uses `keepBuffer: 0`, does not request retina tiles, and does not prefetch.
- The browser sends the User-Agent and caches tiles. This app does not download tiles from the API process.
- `tile.openstreetmap.org` is not a CDN. Set `VITE_MAP_TILE_URL` and `VITE_MAP_ATTRIBUTION` to another provider before a public launch.

## Listing contract

Search types in `src/types/listing.ts` mirror draft PR #8 (`agent/beebc-grok/listing-model` @ `5bc43fe`), which is stacked on PR #3.

- `ListingLocation` latitude and longitude are the map contract. `ListingLocation` has no zip field. The fuzzy `vehicle_key` reads a ZIP from the location label.
- Results group by `vehicle_key` (`VehicleCluster`): a normalized VIN, or a fuzzy hash when the VIN is missing or invalid.
- Fixtures match that PR: the same M3 on Bring a Trailer and eBay with an asking-price drop, a no-VIN RX-7, and an invalid-VIN Legend.
- `deal_score` is not on that model, so the Deal sort follows price.
