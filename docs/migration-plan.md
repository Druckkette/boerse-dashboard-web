# Migration Plan

## 1. Scaffold

Create the isolated `boerse-dashboard-web` repository with Next.js, FastAPI, Postgres, Redis, Docker Compose, CI and dummy API contracts. No Streamlit code is used.

## 2. Sell-Engine

Extract the UI-independent modules from the reference app:

- `sell_decision_metrics.py`
- `sell_decision_rules.py`
- `sell_strategies.py`

Move them under `backend/app/domain/sell`, add Pydantic request/response schemas, and port the existing sell tests as regression coverage.

## 3. Price Cache

Build persistent price storage in Postgres:

- instruments
- price bars
- universes
- symbol mappings

yfinance access becomes an adapter under `backend/app/data_sources`. API endpoints read cached data only.

## 4. Worker

Replace Streamlit/GitHub-Action-coupled workers with queue-backed tasks:

- price refresh
- market breadth
- RS ratings
- SEC/13F artifacts
- ATR position monitor

Celery + Redis is used for queueing. All tasks update `jobs` status rows and are safe to run
with worker concurrency 1 on a Synology NAS.

## 5. Frontend MVP

Connect the dashboard, market view, portfolio table, sell monitor and jobs page to real API data. Keep interactions local and optimistic where possible. The Jobs page polls `/api/v1/jobs`, can start supported task types and cancels queued/running jobs best-effort.

## 6. NAS Deployment

Publish backend and frontend images to GHCR. The NAS runs Postgres, Redis, backend, worker, scheduler and frontend via Docker Compose with persistent volumes and scheduled image pulls. `docs/nas-deployment.md` covers login, updates, backup and rollback.

## 7. Hardening

Add authentication, backups, structured logging, rate limits, data-source failure handling, migration checks, and Hetzner deployment profile with TLS.
