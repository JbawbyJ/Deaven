# Deaven — Deal Intelligence Platform

AI-powered vehicle sourcing and deal scoring platform. Agents surface, score, and triage niche vehicle listings so you buy right every time.

## Architecture

```
backend/
  agents/         # Scout, Vision, Risk, Valuation, Outreach, Scoring
  core/           # Orchestrator (LangGraph), deal graph, trigger engine
  db/             # Supabase client, models, migrations
  api/            # FastAPI routes (deals, watchlist, alerts, outcomes)
  utils/          # Helpers, retry logic, logging

frontend/
  src/
    components/   # DealCard, ScoreBadge, AgentStatus, AlertBanner
    pages/        # Dashboard, DealDetail, Watchlist, Settings
    hooks/        # useDeals, useScore, useAlerts
    store/        # Zustand state
    lib/          # API client, formatters

shared/
  schemas/        # Pydantic + TS shared types (DealPayload, Reports)
```

## Stack

| Layer | Tech |
|---|---|
| Frontend | React + Vite + Tailwind |
| Backend | FastAPI + Python 3.11 |
| Agents | LangGraph + CrewAI |
| DB | Supabase + pgvector |
| Vision | YOLOv8 + Claude Vision API |
| Scraping | Playwright + Firecrawl |
| ML | XGBoost + Stable-Baselines3 (RL) |
| Alerts | Resend (email) + Twilio (SMS) |

## Setup

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in keys

# Frontend
cd frontend
npm install
npm run dev

# Run orchestrator
cd backend
python -m core.orchestrator
```

## Environment Variables

```
ANTHROPIC_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
CARFAX_API_KEY=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
RESEND_API_KEY=
FIRECRAWL_API_KEY=
```
