# SentinelAI

SentinelAI is a security log ingestion and anomaly-detection platform built around a FastAPI backend, a Redis-backed worker pipeline, a Next.js dashboard, and an optional host-side log shipping agent.

The current codebase goes beyond the earlier phase-based backend milestone. It now includes realtime dashboard updates, IP profile analytics, hybrid anomaly scoring, and a separate `sentinel-agent` collector.

## Components

| Component | Stack | Purpose |
|---|---|---|
| Backend API | FastAPI, SQLAlchemy async, PostgreSQL | Log ingestion, alerts, health, metrics, IP analytics |
| Queue layer | Redis | Main queue, processing queue, DLQ, Pub/Sub |
| Alert worker | Async Python | Rule evaluation, statistical scoring, isolation scoring, alert creation |
| Dashboard | Next.js 16, React 19, Recharts | Realtime monitoring UI |
| Sentinel Agent | Python | Tails host log files and forwards them to `/logs` |

## Current Architecture

```text
Host logs -> Sentinel Agent -> POST /logs -> PostgreSQL + Redis queue
                                              |
                                              v
                                        Alert worker
                                              |
                   +--------------------------+---------------------------+
                   |                          |                           |
                   v                          v                           v
              Rule engine              Statistical score          IsolationForest score
                   \__________________________|___________________________/
                                              v
                                     Combined risk scoring
                                              v
                                    Alert persistence + Pub/Sub
                                              v
                              Dashboard polling + /ws/dashboard stream
```

## Key Features

- Async log ingestion via `POST /logs`
- Redis-backed queueing with processing queue recovery and dead-letter queue handling
- Rule-based detection for high-signal events and IP burst activity
- Hybrid anomaly scoring using weighted rule, statistical, and isolation-model signals
- Realtime dashboard updates over WebSocket plus periodic metrics broadcasts
- Health diagnostics, queue visibility, metrics timeseries, and per-IP profiling
- Optional API key protection using `X-API-Key`
- Separate lightweight Sentinel agent for forwarding host log files

## Important Deployment Constraint

The alert worker currently keeps multiple scoring and baseline stores in memory. Because of that, the current hybrid anomaly pipeline should run as a single worker for consistent results.

Keep `worker=1` unless you first redesign the in-memory state into shared storage.

## Repository Layout

```text
SentinelAI/
├── app/                    # FastAPI app, models, services, worker, middleware
├── tests/                  # Backend test suite
├── sentinel-frontend/      # Next.js dashboard
├── sentinel-agent/         # Host-side log shipping agent
├── docker-compose.yml      # Redis + backend + worker + frontend
├── Dockerfile              # Backend container
├── requirements.txt        # Backend Python dependencies
└── .env.example            # Backend environment template
```

## Prerequisites

- Python 3.11+ for local backend and agent development
- Node.js 20+ for the frontend
- Docker Desktop if you want the containerized setup
- PostgreSQL database reachable via `DATABASE_URL`
- Redis instance, local or containerized

## Backend Configuration

Copy `.env.example` to `.env` and set at least:

```env
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@db.YOUR_PROJECT.supabase.co:5432/postgres
REDIS_URL=redis://localhost:6379/0
API_KEY=
DEBUG=false
RETRAIN_COOLDOWN_SECONDS=300
```

Notes:

- `API_KEY` empty means auth is disabled. That is the default dev mode.
- Additional anomaly-scoring tunables live in [app/config.py](C:/Projects/SentinelAI/app/config.py).
- The backend creates tables on startup via `Base.metadata.create_all()`.

## Run Locally

### 1. Backend API

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

pip install -r requirements.txt
copy .env.example .env
```

Start Redis if needed:

```bash
docker run -d -p 6379:6379 redis:7-alpine
```

Start the API:

```bash
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000` and the OpenAPI docs at `http://localhost:8000/docs`.

### 2. Alert Worker

Run the worker in a separate terminal:

```bash
.venv\Scripts\activate
python -m app.workers.alert_worker
```

### 3. Frontend Dashboard

```bash
cd sentinel-frontend
npm install
npm run dev
```

The dashboard runs at `http://localhost:3000`.

Set `NEXT_PUBLIC_API_BASE` if your backend is not on `http://localhost:8000`.

### 4. Sentinel Agent

```bash
cd sentinel-agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python agent.py --config config.yaml
```

Agent details and config are documented in [sentinel-agent/README.md](C:/Projects/SentinelAI/sentinel-agent/README.md).

## Run With Docker Compose

```bash
copy .env.example .env
docker compose up --build
```

Default services:

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3000`
- Redis: `localhost:6379`

Compose currently starts one worker, which matches the single-worker requirement of the current anomaly pipeline.

The Sentinel agent is not included in the root Compose file. Run it separately where the host logs exist.

## API Surface

### Ingestion

- `POST /logs`
  Ingests a single log event and enqueues it for asynchronous alert evaluation.

Example body:

```json
{
  "source": "firewall",
  "log_level": "ERROR",
  "message": "Unauthorized access attempt",
  "timestamp": "2026-03-11T12:00:00Z",
  "ip_address": "192.168.1.100"
}
```

### Alerts

- `GET /alerts`
- `GET /alerts?severity=HIGH`
- `GET /alerts?limit=50&offset=0&sort=timestamp_desc`

Supported sort values:

- `timestamp_desc`
- `timestamp_asc`
- `risk_score_desc`
- `risk_score_asc`

### Observability

- `GET /health`
- `GET /metrics`
- `GET /metrics/timeseries?window=15`
- `GET /queues`
- `GET /dlq`
- `GET /ip/{ip}/profile`
- `WS /ws/dashboard`

## Detection Model

The worker evaluates each log in roughly this order:

1. Rule engine
2. Statistical anomaly scoring
3. IsolationForest anomaly scoring
4. Weighted risk combination
5. Alert creation when severity is `LOW`, `MEDIUM`, or `HIGH`

Current rule highlights:

- `log_level == ERROR` triggers a `HIGH`
- message containing `failed login` triggers a `HIGH`
- message containing `unauthorized` triggers a `HIGH`
- more than `IP_RATE_THRESHOLD` logs from one IP inside `IP_RATE_WINDOW_SECONDS` triggers a `MEDIUM`

Scoring weights are configurable in [app/config.py](C:/Projects/SentinelAI/app/config.py):

- `RULE_WEIGHT`
- `STAT_WEIGHT`
- `ISO_WEIGHT`
- `ANOMALY_THRESHOLD_LOW`
- `ANOMALY_THRESHOLD_MEDIUM`
- `ANOMALY_THRESHOLD_HIGH`

## Auth Behavior

When `API_KEY` is set, HTTP endpoints require the `X-API-Key` header and the WebSocket endpoint accepts either the header or an `api_key` query parameter.

When `API_KEY` is empty, auth is disabled for local development.

Important frontend note:

- The current dashboard fetch layer does not attach `X-API-Key`.
- In practice, the dashboard works out of the box when backend auth is disabled, or when a proxy injects auth on its behalf.

## Sentinel Agent Summary

The agent in `sentinel-agent/`:

- polls configured files for appended lines
- handles simple rotation and truncation
- derives `log_level`, `timestamp`, and `ip_address` heuristically
- batches outgoing HTTP sends
- retries transient failures with exponential backoff

Use it when you want to forward system logs such as auth, syslog, or nginx access logs from another host into SentinelAI.

## Testing

Run backend tests with:

```bash
pytest
```

The test suite covers auth, ingestion, metrics, middleware, alerts, rule evaluation, and scoring behavior.
