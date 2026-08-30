# Deaven — Deal Intelligence Platform

AI-powered vehicle sourcing and deal scoring. Agents surface, score, and triage niche vehicle listings so you buy right every time.

## What runs today vs the target stack

The first commit sketched the full platform (LangGraph, Supabase, YOLOv8, Playwright scrapers, XGBoost/RL, Resend/Twilio). That stack is **not** required to try the product locally.

This repo now has a **local MVP** that matches the Swagger contract in `Deaven API - Swagger UI.pdf`:

| Working without production keys | Still aspirational / partial |
|---|---|
| FastAPI deals, watchlists, stats | Live BaT / eBay / Classic.com / TCV scrapers |
| React feed, deal detail, watchlist, pipeline | LangGraph orchestrator + Claude vision/narratives |
| Local JSON store + seeded catalog | Supabase + pgvector |
| Heuristic scoring (swap-in for live agents) | YOLOv8, XGBoost, RL rewards |
| Catalog scout (`SCOUT_BACKEND=local`) | Resend / Twilio alerts |

Live scrapers and agent modules remain in the tree. They are imported only when you opt into `SCOUT_BACKEND=live` or `PIPELINE_MODE=full`.

## Local MVP (core flow)

A reviewer can run backend + frontend, open the deal feed, click into a scored listing, ingest another catalog URL, and save a watchlist. No Anthropic, Supabase, eBay, or Carfax key is required.

### 1. Backend

From the repo root:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env   # defaults are enough

PYTHONPATH=. uvicorn backend.api.main:app --reload --port 8000
```

- API: http://127.0.0.1:8000
- Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI: http://127.0.0.1:8000/openapi.json

On first boot the local store is seeded with five scored catalog deals and an `E46 M3 Hunt` watchlist. Data is written to `backend/data/local_store.json` (gitignored).

### 2. Frontend

```bash
cd frontend
cp .env.example .env.local   # optional; defaults to http://localhost:8000
npm install
npm run dev
```

Open http://localhost:5173

### 3. Walk the core flow

1. **Feed** — seeded deals with scores/tiers (Fire / Strong / Watch / Pass). Fire count comes from `GET /stats/pipeline`.
2. **Run scout** — Dashboard and Pipeline call `POST /scout/run` and show `last_scout` from `/health`. Scheduler stays opt-in (`SCOUT_SCHEDULER`).
3. **Detail** — score breakdown, narrative, acquire/pass, and sale outcome (`PATCH /deals/{id}/outcome`).
4. **Ingest** — paste `local://supra-1998` (or any catalog URL) in the navbar. The deal is scored immediately and the feed refreshes.
5. **Watchlist / Pipeline** — create a saved search; pipeline totals come from the same store.

Catalog slugs accepted by `POST /deals/ingest`:

- `local://bmw-m3-2003`
- `local://rx7-1993`
- `local://911-2004`
- `local://supra-1998`
- `local://s2000-2006`

Unknown URLs still ingest as a heuristic manual listing (source detected from the host when possible).

### Tests

```bash
source .venv/bin/activate
PYTHONPATH=. pytest backend/tests -q
```

## Environment

See `backend/.env.example`. Local defaults:

```
PIPELINE_MODE=local
SCOUT_BACKEND=local
STORE_BACKEND=local
SEED_DEMO_DEALS=true
```

Optional later:

| Variable | When you need it |
|---|---|
| `SUPABASE_URL` / `SUPABASE_KEY` | `STORE_BACKEND=supabase` |
| `ANTHROPIC_API_KEY` | LLM narratives / vision (`PIPELINE_MODE=full`) |
| `EBAY_APP_ID` | Live eBay Finding API scout |
| `FIRECRAWL_API_KEY`, `CARFAX_API_KEY`, Twilio, Resend | Live scrape / title / alerts |

`pip install -r backend/requirements-full.txt` pulls the heavier target stack. Do not install it for the local walkthrough.

## Architecture

```
backend/
  agents/         # Scout, local heuristic pipeline, live Vision/Risk/Valuation/Scoring
    scrapers/     # BaT, eBay, Classic.com, TCV (opt-in)
  core/           # Settings, LangGraph orchestrator (full mode)
  db/             # Local JSON store; optional Supabase
  api/            # FastAPI routes (Swagger contract)
  data/           # Catalog fixtures

frontend/
  src/
    components/   # DealCard, ScoreBadge, AgentReport
    pages/        # Dashboard, DealDetail, Watchlist, Pipeline
    hooks/        # useDeals, useStats
    store/        # Zustand
    lib/          # API client, formatters

shared/
  schemas/        # DealPayload and agent reports
```

## Target stack (README original)

| Layer | Tech |
|---|---|
| Frontend | React + Vite + Tailwind |
| Backend | FastAPI + Python 3.11+ |
| Agents | LangGraph + CrewAI |
| DB | Supabase + pgvector |
| Vision | YOLOv8 + Claude Vision API |
| Scraping | Playwright + Firecrawl |
| ML | XGBoost + Stable-Baselines3 (RL) |
| Alerts | Resend (email) + Twilio (SMS) |

## Swapping the stub scout

`backend/agents/scout.py` already has the live scraper map. Set `SCOUT_BACKEND=live` (and install `requirements-full.txt` plus source keys) to use BaT/eBay/Classic.com/TCV. eBay Finding keywords for the seeded BMW M3 2001–2006 hunt include **E46**. BaT / Classic.com / TCV failures are isolated — one source cannot fail the cycle. No Cloudflare stealth. The dashboard and `/deals*` contract do not change.
