# SentinelAI – Phase 2

Production-grade security log ingestion and rule-based alerting platform.  
Phase 2 adds a distributed, event-driven architecture with Redis queues, worker scaling, and observability.

---

## Architecture

| Layer | Technology |
|-------|-----------|
| API | FastAPI |
| ORM | SQLAlchemy 2.0 (async) |
| DB driver | asyncpg |
| Database | Supabase-hosted PostgreSQL |
| Queue | Redis (redis.asyncio) |
| Worker | Async Python (horizontally scalable) |
| Containerisation | Docker Compose |
| Frontend | Next.js 16 (App Router) + Tailwind (TypeScript) |

### Event Flow

```
Client → POST /logs → Save log to DB → Enqueue to Redis
                                            ↓
                              Alert Worker (1..N instances)
                                            ↓
                              Evaluate rules → Insert alert (idempotent)
                              On failure → Retry (exp. backoff) → DLQ
```

---

## Key Features (Phase 2)

- **At-least-once delivery** – Redis BRPOPLPUSH atomic move pattern
- **Idempotent alert creation** – Unique constraint on `alerts.log_id`
- **Retry + DLQ** – Exponential backoff, max 3 retries, then dead-letter queue
- **Crash recovery** – Orphaned processing-queue items recovered on worker start
- **Horizontal worker scaling** – `docker compose up --scale worker=3`
- **JSON structured logging** – Every log line is machine-parseable JSON
- **Request ID middleware** – `X-Request-ID` header propagation
- **Metrics endpoint** – `GET /metrics` for logs_received, alerts_created, retries, dlq_count

---

## Getting your Supabase DATABASE_URL

1. Go to your Supabase project → **Settings → Database**.
2. Copy the **Connection string** (URI format).
3. Replace the scheme with `postgresql+asyncpg://` so SQLAlchemy uses the async driver.

Example:

```
postgresql+asyncpg://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres
```

4. Place it in a `.env` file at the project root (see `.env.example`).

---

## Run locally (without Docker)

```bash
cd sentinel_ai

# Create virtualenv
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

pip install -r requirements.txt

# Set env (or create .env)
copy .env.example .env        # then edit .env with real credentials

# Start Redis (required)
docker run -d -p 6379:6379 redis:7-alpine

# Start API
uvicorn app.main:app --reload

# Start worker (separate terminal)
python -m app.workers.alert_worker
```

The API will be available at `http://localhost:8000`.  
Interactive docs at `http://localhost:8000/docs`.

---

Frontend (local)

```
# In a separate terminal, run the Next.js frontend
cd sentinel-frontend
npm install
npm run dev
```

The frontend is configured to call the API base defined by `NEXT_PUBLIC_API_BASE` (defaults to `http://localhost:8000` in `sentinel-frontend/.env.local`).

---

## Run with Docker Compose

```bash
cd sentinel_ai

# Create .env with your DATABASE_URL
copy .env.example .env        # edit with real credentials

docker compose up --build

# Scale workers horizontally
docker compose up --scale worker=3
```

By default the Compose setup now includes a lightweight Next.js frontend served on port 3000. After `docker compose up --build` the frontend will be available at `http://localhost:3000` and the API at `http://localhost:8000`.

If you only want to build or restart the frontend container separately:

```bash
docker compose build frontend
docker compose up -d frontend
```

Environment variables used by the frontend:

- `NEXT_PUBLIC_API_BASE` — base URL for the API (defaults to `http://localhost:8000` in `sentinel-frontend/.env.local`).

Note: the backend enables CORS for `http://localhost:3000` so the frontend can call the API directly from the browser.

---

## API Endpoints

### Health check

```
GET /health
```

### Ingest a log

```
POST /logs
Content-Type: application/json

{
  "source": "firewall",
  "log_level": "ERROR",
  "message": "Unauthorized access attempt",
  "timestamp": "2026-02-28T12:00:00Z",
  "ip_address": "192.168.1.100"
}
```

Returns the stored log. Alert is created asynchronously by the worker.

### List alerts

```
GET /alerts
GET /alerts?severity=HIGH
```

### Metrics

```
GET /metrics
```

Returns counters: `logs_received`, `alerts_created`, `retries`, `dlq_count`.

### Dead-letter queue inspection

```
GET /dlq
```

### Queue lengths

```
GET /queues
```

---

## Rule Engine

| Severity | Condition |
|----------|-----------|
| **HIGH** | `log_level == "ERROR"` |
| **HIGH** | message contains "failed login" |
| **HIGH** | message contains "unauthorized" |
| **MEDIUM** | > 5 logs from the same IP within 60 s |

---

## Project Structure

```
sentinel_ai/
├── app/
│   ├── main.py                # FastAPI app + lifespan
│   ├── config.py              # Pydantic settings
│   ├── database.py            # Async engine & session
│   ├── logging_config.py      # JSON structured logging
│   ├── metrics.py             # In-memory counters + /metrics
│   ├── middleware/
│   │   └── request_id.py      # X-Request-ID middleware
│   ├── models/
│   │   ├── log.py             # logs table
│   │   └── alert.py           # alerts table (unique log_id)
│   ├── schemas/
│   │   ├── log.py             # Request/response DTOs
│   │   └── alert.py
│   ├── services/
│   │   ├── log_service.py     # Ingestion + enqueue
│   │   ├── queue_service.py   # Redis queue, DLQ, recovery
│   │   └── rule_engine.py     # Rule evaluation logic
│   ├── workers/
│   │   └── alert_worker.py    # Async worker loop
│   └── api/
│       ├── logs.py            # POST /logs
│       └── alerts.py          # GET /alerts
├── tests/
│   ├── conftest.py
│   ├── test_logs.py
│   ├── test_alerts.py
│   ├── test_metrics.py
│   ├── test_middleware.py
│   └── test_rule_engine.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```
