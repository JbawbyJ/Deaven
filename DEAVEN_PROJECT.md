# Deaven — Deal Intelligence Platform

**Project documentation — build session log**
**Last updated: August 2026**

---

## What Deaven Is

Deaven is an AI-powered vehicle deal intelligence platform for a boutique niche-car dealership. Agents continuously surface, score, and triage vehicle listings across auction sites, marketplaces, and JDM import sources so acquisitions are data-driven instead of gut-feel. The mental model: Maven/Palantir applied to vehicle sourcing — agents as the sensing layer, a dashboard as the command center.

```
[ Data Sources ]  →  [ Agent Layer ]  →  [ Intelligence Layer ]  →  [ Dashboard ]
```

---

## Business Model Context

**Positioning:** Curated boutique — selling provenance and trust, not volume.

**Revenue streams:**
1. Retail margin — target 15–25% gross on niche/collector units, low volume (5–15 cars/month)
2. Consignment — 6–10% of sale price, zero acquisition capital
3. Sourcing-as-a-service — flat fee ($1,500–$3,000) or 3–5% of purchase price
4. Acquisition advisory — buyer-side retainer, no inventory risk
5. Membership/concierge tier — $200–$500/mo for first-look access and wishlist monitoring

**Niche angles:** JDM imports (25-year rule), Euro grey market, single-marque focus, low-mileage modern classics (E46 M3, FD RX-7, MK4 Supra era).

**The moat:** a 24/7 agent network that surfaces and pre-qualifies deals before competitors see them. TCV (Japanese auction aggregator) monitoring is a specific edge — almost no US boutique dealers watch it systematically.

---

## Architecture

### Agent Graph

```
                    ORCHESTRATOR (LangGraph)
                            │
                      SCOUT AGENT
                Crawl → Ingest → Dedupe
                            │
                      TRIAGE GATE
             (price/marque/photo pre-filter)
                            │
        ┌───────────────────┼───────────────────┐
   VISION AGENT        RISK AGENT        VALUATION AGENT
  (photo analysis)   (VIN/title/recall)  (comps + margin)
        └───────────────────┼───────────────────┘
                            │
                     SCORING ENGINE
              (weighted composite + narrative)
                            │
                      SCORE GATE
          <40 discard │ 40–69 watchlist │ 70+ action
                            │
                    OUTREACH AGENT
              (draft seller contact, human review)
                            │
                   DASHBOARD EVENT
              (persist to DB, alert on Fire)
```

Vision, Risk, and Valuation run **concurrently** via `asyncio.gather`. Target end-to-end runtime: under 45 seconds per deal.

### Deal Score Model

Weighted composite, 0–100:

| Dimension | Weight | Source |
|---|---|---|
| Price (vs. market comps) | 30% | Valuation Agent |
| Provenance (history/title) | 25% | Risk Agent |
| Demand (liquidity signals) | 20% | Valuation Agent |
| Condition (photo analysis) | 15% | Vision Agent |
| Margin (profit after all-in costs) | 10% | Valuation Agent |

**Tiers:** 85–100 Fire (act now) · 70–84 Strong Buy · 55–69 Watchlist · 40–54 Pass · 0–39 Discard

**Dynamic adjustments:** price drops (+8), watch-count spikes (+5), stale listings (−4 to −8), low vision confidence (−5). Hard disqualifiers (salvage/flood/odometer rollback) zero the score immediately.

**LLM narrative:** every scored deal gets a 2–3 sentence advisory note (Claude Haiku) — tier, key reason, biggest risk, next action.

### ML/RL Roadmap (phased)

| Phase | Milestone |
|---|---|
| MVP | Rule-based scoring + Claude Vision |
| v2 | Log outcomes, XGBoost on first 50 deals |
| v3 | SHAP feature analysis |
| v4 | PPO agent (Stable-Baselines3), offline RL, shadow mode |
| v5 | RL live with human-in-the-loop override |

Outcome fields (`human_decision`, `outcome_margin_actual`, `outcome_days_to_sell`, `outcome_lemon`) are captured in the schema from day one to feed this loop.

---

## Tech Stack

| Layer | Tech |
|---|---|
| Frontend | React 18 + Vite + Tailwind + Zustand + React Query |
| Backend | FastAPI + Python (venv) |
| Agent orchestration | LangGraph |
| LLM | Anthropic API (Claude Vision for photos, Haiku for narratives) |
| DB | Supabase (JSONB `deals` table, upsert by `deal_id`) |
| Scraping | Playwright, Firecrawl, eBay Finding API, Apify (planned) |
| Vision (planned) | YOLOv8 defect detection pre-pass |
| ML (planned) | XGBoost, SHAP, Stable-Baselines3 |
| Alerts (planned) | Resend (email), Twilio (SMS) |

---

## Project Structure

```
Deaven/
  README.md
  .gitignore                  # excludes .env, venv/, node_modules/
  shared/
    schemas/
      deal.py                 # DealPayload + all data contracts (single source of truth)
  backend/
    .env                      # ANTHROPIC_API_KEY, SUPABASE_URL/KEY, EBAY_APP_ID (never committed)
    .env.example              # committed template
    requirements.txt
    agents/
      scout.py                # coordinates scrapers, dedupe, pre-filter
      vision.py               # Claude Vision photo analysis + YOLOv8 hook
      risk.py                 # NHTSA recalls (live), VIN decode, Carfax stub
      valuation.py            # comp aggregation, demand scoring, margin model
      scoring.py              # weighted composite + narrative generation
      scrapers/
        ebay.py               # eBay Finding API (category 6001)
        bat.py                # Bring a Trailer — Playwright DOM scraping + sold comps
        classic_com.py        # comp client + marketplace scraper (Cloudflare-protected)
        tcv.py                # tc-v.com JDM — JPY→USD, 25-year rule, auction sheets
    core/
      orchestrator.py         # LangGraph pipeline, scheduler, batch processing
    api/
      main.py                 # FastAPI routes
    db/
      client.py               # Supabase upsert/fetch, JSONB payload storage
  frontend/
    src/
      pages/                  # Dashboard, DealDetail, Watchlist, Pipeline
      components/             # DealCard, ScoreBadge, TierBadge, StatCard, Navbar, AgentReport
      hooks/                  # useDeals (30s polling), useStats
      store/                  # Zustand
      lib/                    # axios client, formatters
```

### API Routes

| Route | Purpose |
|---|---|
| `GET /health` | Liveness check |
| `POST /deals/ingest` | Manual URL ingest → saves + triggers pipeline in background |
| `GET /deals` / `GET /deals/{id}` | Feed and full deal payload |
| `PATCH /deals/{id}/outcome` | Record sale outcome (feeds ML) |
| `POST /deals/{id}/decision` | Acquire / pass / watchlist decision |
| `GET/POST/DELETE /watchlists` | Saved search filters |
| `GET /stats/pipeline` | Dashboard metrics |

### Frontend Design System

Dark intelligence-platform aesthetic: bg `#0a0a0a`, surface `#111111`, borders `#1f1f1f`, gold accent `#c9a84c`. Tier colors: Fire `#ef4444` (pulsing badge + red glow), Strong `#f97316`, Watch `#eab308`, Pass `#6b7280`. Fonts: Inter (UI) + IBM Plex Mono (data). Frontend proxies `/api` → `localhost:8000`; feed polls every 30s.

---

## Windows Setup Guide (as-built)

Environment: Windows 11, PowerShell, Cursor, Python 3.14, Node LTS.

```powershell
# Backend
cd Deaven\backend
python -m venv venv
venv\Scripts\activate                 # if blocked: Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
pip install -r requirements.txt
.\venv\Scripts\python.exe -m playwright install chromium
copy .env.example .env                # then fill in real keys

# Run API (from repo ROOT, not backend/)
cd ..
.\backend\venv\Scripts\python.exe -m uvicorn backend.api.main:app --reload
# → http://localhost:8000  (docs at /docs)

# Frontend (second terminal)
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

### Hard-won environment lessons

- **Always invoke the venv Python explicitly** (`.\backend\venv\Scripts\python.exe`) — plain `python` resolves to the Windows Store / system install and packages appear "missing."
- Every package folder needs `__init__.py` (`backend/`, `backend/api/`, `backend/core/`, `backend/agents/`, `backend/agents/scrapers/`, `backend/db/`, `shared/`, `shared/schemas/`). The original `ModuleNotFoundError: backend.api` was a missing folder + missing init files.
- A `deaven.pth` file in `venv\Lib\site-packages` containing the repo root path makes absolute imports (`from backend...`, `from shared...`) work regardless of cwd.
- `pyiceberg` (pulled by newer `supabase`) fails to build without MS C++ Build Tools — pin `supabase==2.3.0` or accept the httpx version-conflict warnings (harmless for now).
- eBay Finding API free tier rate-limits per App ID per day — use a **dedicated Deaven keyset**, don't share with other projects.
- Supabase backend client must use the **service_role** secret, not the anon key. Watch for quotes/spaces/truncation in `.env`.
- OneDrive-synced folders can cause file-lock weirdness with agentic tools — prefer `C:\dev\deaven` on new machines.

### Supabase schema

```sql
create table public.deals (
  deal_id    text primary key,
  payload    jsonb not null,
  updated_at timestamptz not null default now()
);
create index deals_payload_gin on public.deals using gin (payload);
alter table public.deals enable row level security;
```

Full `DealPayload` stored as JSONB; upsert on `deal_id` lets the pipeline re-save as agents fill in reports. Denormalized columns (`deal_tier`, `deal_score`, `status`) planned for feed filtering.

---

## Current State

### Done ✅
- Full schema layer (`DealPayload`, agent reports, score components, watchlist filters)
- LangGraph orchestrator: triage → parallel agents → scoring → outreach → dashboard event, with graceful degraded-report fallbacks and concurrency-limited batching
- All five agents implemented (Risk uses live free NHTSA APIs; Carfax is a stub pending partner access)
- Scoring engine with dynamic adjustments + Haiku narratives
- Supabase persistence wired into ingest + pipeline
- FastAPI running clean; all routes live in Swagger
- Scrapers built: eBay (Finding API), BaT (Playwright + sold comps), Classic.com (comp client + marketplace), TCV (JDM w/ 25-year rule, JPY→USD, Claude Vision auction-sheet parsing)
- Comp fallback chain in ValuationAgent: Classic.com → BaT
- React frontend scaffolded and running (Dashboard, DealDetail, Watchlist, Pipeline)

### Open issues ⚠️
1. **Supabase `Invalid API key`** on ingest — `.env` key needs re-pasting/verification (service_role, no quotes, full length). This currently blocks the first end-to-end deal.
2. **eBay rate limit** — was sharing an App ID with another project; create a dedicated Deaven production keyset.
3. **Classic.com Cloudflare** — headless Playwright gets challenged; needs residential proxies or session cookies for reliable production runs.
4. **BaT sold-search quirk** — `?sold=1` search loads empty headless; scraper falls back to `/{make}/{model}/` (324 results confirmed on `/auctions/results/`).
5. **TCV regional redirects** — `stock/?maker=` sometimes redirects by IP; `/used_car/` path fallback in place. TCV not yet added to `SOURCE_MAP`.

### Next steps 🎯
1. Fix Supabase key → run first full ingest → deal appears in dashboard feed
2. Dedicated eBay keyset → live eBay listings flowing
3. Wire scheduler (15-min scout cycles) with first real watchlist
4. Implement `GET /deals` list query + `/stats/pipeline` aggregation from Supabase (currently stubs)
5. Facebook Marketplace via Apify; Hemmings/Cars.com/Autotrader via Firecrawl
6. Alerts (Resend/Twilio) on Fire-tier deals
7. Begin outcome logging → XGBoost baseline at ~50 closed deals

---

## Multi-Tool Workflow

| Tool | Role |
|---|---|
| **Claude (chat)** | Architecture, specs, scoring/agent design, debugging reasoning, Cursor prompts |
| **Cursor** | In-editor code writing, refactors, find/replace, Composer (Agent mode) builds |
| **Claude Code** | Terminal-driven agentic loops — run, read traceback, fix, rerun (e.g., "debug why Supabase rejects my API key in backend/db/client.py") |

Pattern that worked: spec in Claude → paste structured prompt into Cursor Agent mode → review output in Claude → wire + test in terminal.

**GitHub flow:** private repo `deaven`; `.gitignore` excludes `.env`, `venv/`, `node_modules/`; verify with `git status` before first commit (secrets in history = rotate everything). Clone on target machine, recreate `.env` from `.env.example`, rebuild venv + `npm install`, then `claude` → `/init` to generate CLAUDE.md.

**CLAUDE.md seeds:** venv-explicit run command from repo root, package init-file requirement, Supabase service_role note, current open issues above.

---

## Key Design Decisions (rationale log)

- **Single `DealPayload` contract** flowing through every agent — no tight coupling, agents fail independently with degraded reports rather than killing the pipeline.
- **JSONB over normalized tables** initially — schema is deep and evolving; index/denormalize only what the feed queries need.
- **Triage gate before expensive agents** — rule-based kill of bad listings before spending Vision/API tokens.
- **Upsert-by-deal_id persistence** — record exists from ingest; pipeline progressively enriches it, so a crash never loses the deal.
- **Comp aggregation with fallback chain** — Classic.com (cross-platform breadth) primary, BaT direct as fallback; scoring degrades to neutral rather than failing when comps are empty.
- **Outcome fields in schema from day one** — the RL flywheel needs training data before the RL exists.
- **Shadow mode before autonomy** — the RL agent recommends alongside human decisions for ~3 months and is only promoted when it beats the human baseline.
