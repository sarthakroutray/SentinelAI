# 🛡️ SentinelAI

**SentinelAI** is an advanced, real-time security log ingestion and anomaly-detection platform. It ingests log data from host systems, analyzes them using a hybrid ML/rule-based pipeline, and surfaces threats through a production-grade React dashboard with real-time WebSocket streaming.

---

## 🎯 What It Does

- **Real-time Log Ingestion**: Accepts logs via HTTP API; instantly queues them for async evaluation.
- **Hybrid Anomaly Scoring**: Combines rule-based detection, statistical heuristics, and Isolation Forest ML models.
- **Live Dashboard**: Next.js 16 + React 19 frontend with WebSocket streaming + periodic REST API polling.
- **IP Profiling**: Tracks per-IP error ratios, risk scores, and alert densities.
- **Queue Resilience**: Dead-letter queue (DLQ) support for failed messages; automatic recovery on worker restart.

---

## 📋 Requirements

- **Python 3.11+** (backend & worker)
- **Node.js 20+** (frontend)
- **PostgreSQL 16+** (database)
- **Redis 7+** (message queue)
- **Docker & Docker Compose** (recommended)

---

## 🚀 Quick Start

### Docker Compose (Recommended)

```bash
git clone <repo>
cd SentinelAI
docker compose up --build
```

**Endpoints:**
- Dashboard: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Local Development

```bash
# Backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Worker (separate terminal)
python -m app.workers.alert_worker

# Frontend (separate terminal)
cd sentinel-frontend
npm install
npm run dev
```

---

## 🔌 API Examples

**Ingest a log:**
```bash
curl -X POST http://localhost:8000/logs \
  -H "Content-Type: application/json" \
  -d '{
    "source": "firewall",
    "log_level": "ERROR",
    "message": "Unauthorized access",
    "timestamp": "2026-03-20T12:00:00Z",
    "ip_address": "192.168.1.10"
  }'
```

**Get alerts:**
```bash
curl http://localhost:8000/alerts?limit=50&severity=HIGH
```

**Stream alerts (WebSocket):**
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/dashboard');
ws.onmessage = e => console.log(JSON.parse(e.data));
```

---

## 📁 Project Structure

```
app/                  # FastAPI backend
├── api/              # REST endpoints
├── models/           # SQLAlchemy ORM
├── services/         # Business logic & ML pipeline
├── workers/          # Alert worker
└── middleware/       # Auth, logging, etc.

sentinel-frontend/    # Next.js dashboard
├── src/app/          # Pages & layout
└── src/components/   # React components

tests/                # Pytest suite (72+ tests)
docker-compose.yml    # Full stack
```

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and configure:

```dotenv
DATABASE_URL=postgresql+asyncpg://sentinel:password@localhost/sentinelai
REDIS_URL=redis://localhost:6379/0
API_KEY=          # Leave empty for dev mode
DEBUG=false
RETRAIN_COOLDOWN_SECONDS=300
```

---

## 🧪 Testing

```bash
pytest -v
```

---

## 📚 Learn More

- See [docker-compose.yml](docker-compose.yml) for full-stack setup
- See [Architecture.md](Architecture.md) for technical deep dive
- See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines

---

Made with ❤️ for security teams
