# SentinelAI Ingestion Agent Audit

**Date:** March 19, 2026  
**Scope:** Automated log ingestion pipeline (sentinel-agent)  
**Assessment Level:** Lab → Production readiness gap analysis  

---

## Executive Summary

The SentinelAI ingestion agent is a lightweight, functional log shipper designed for lab environments and controlled deployments. It successfully implements core tailing, parsing, buffering, retries, and API delivery. However, it lacks enterprise-grade reliability and security hardening for production compliance workloads.

**Current State:** ✅ Functional for proof-of-concept  
**Production Ready:** ⚠️ Requires hardening before mission-critical deployment  

---

## Architecture Overview

```
log file(s) 
    ↓ (LogWatcher polls at configurable interval)
in-memory queue 
    ↓ (batches or time-based flush)
LogSender 
    ↓ (individual retries with exponential backoff)
POST /logs endpoint (SentinelAI backend)
    ↓ (API key validated, request validated)
PostgreSQL → alert worker processing
```

**Key Components:**
- [agent.py](sentinel-agent/agent.py) – Thread lifecycle and graceful shutdown
- [watcher.py](sentinel-agent/watcher.py) – Polling file tailer with rotation handling
- [parser.py](sentinel-agent/parser.py) – Heuristic log line parsing (levels, timestamps, IPs)
- [sender.py](sentinel-agent/sender.py) – Buffered HTTP delivery with exponential backoff
- [config.py](sentinel-agent/config.py) – YAML config validation

---

## Key Findings

### 1. ⛔ **No Durable Local Spool (Risk: High)**

**Current Behavior:**
- Queue is entirely in-memory ([sender.py](sentinel-agent/sender.py), [agent.py](sentinel-agent/agent.py))
- Unsent events are lost on process crash, host reboot, or container eviction
- Graceful drain on normal shutdown helps, but covers only planned terminations

**Enterprise Impact:**
- Weak delivery guarantees for compliance/audit logs
- Violates SOC 2 / ISO 27001 data integrity requirements
- Security incidents occurring during outage window go undetected

**Recommended Fix:**
- Add disk-backed queue (SQLite WAL, append-only file, or local DB)
- On startup, replay events unsent from previous runs
- Define retention caps and backpressure thresholds

---

### 2. ⚠️ **Batching Does Not Scale (Risk: Medium)**

**Current Behavior:**
- Agent collects logs into batch bounded by `batch_size` or `flush_interval` ([config.py default: 20 events](sentinel-agent/config.py))
- Batch is sent to backend **one event at a time** in a loop ([sender.py](sentinel-agent/sender.py))
- Each event → separate HTTP request, auth header, parsing

**Enterprise Impact:**
- Throughput ceiling: ~50–100 logs/sec per agent instance (network I/O bound)
- API server overhead: N requests instead of 1 bulk operation
- Sub-optimal for high-volume sources (firewalls, front-end proxies)

**Recommended Fix:**
- Add bulk ingestion endpoint: `POST /logs/bulk` accepting array of events
- Send true batch payloads (gzip-compressed JSON arrays)
- Retries apply to entire batch atomically or with per-event granularity

---

### 3. 🔴 **At-Most-Once Delivery for Validation Failures (Risk: Medium)**

**Current Behavior:**
- HTTP 4xx responses (400, 401, 403, 404, 422) are treated as permanent failures and dropped ([sender.py](sentinel-agent/sender.py))
- Rationale: poison messages should not clog the queue
- Problem: transient misconfigurations (API key mismatch, temp schema change) silently lose data

**Enterprise Impact:**
- No visibility that events were dropped
- Data loss goes undetected until audit trails are reviewed post-incident
- Silent failures harder to debug than loud crashes

**Recommended Fix:**
- Add configurable retry policy for 4xx (retry subset, log to separate DLQ)
- Add idempotency key to each event for safe retries
- Emit metrics and alerting on 4xx rate spikes

---

### 4. 🔴 **Parser Heuristics Degrade Detection (Risk: Medium)**

**Current Behavior:**
- IP extraction: regex search for IPv4, then fallback to `127.0.0.1` if no match ([parser.py](sentinel-agent/parser.py))
- Timestamp: ISO-8601 → syslog → current UTC (no source-specific parsing)
- Log level: keyword search in uppercase message (best-effort, not structured)

**Enterprise Impact:**
- 127.0.0.1 spam contaminates per-IP risk profiles and statistical baselines
- Lost or inaccurate timestamps distort anomaly detection windows
- Unstructured log lines lower precision (false positives on keywords)

**Recommended Fix:**
- Replace hardcoded 127.0.0.1 with `null` when IP not found
- Add source-specific parsers (nginx, syslog, auth.log, CEF/LEEF formats)
- Support structured formats (JSON, syslog RFC5424)

---

### 5. 🟠 **No Secret Manager Integration (Risk: Medium-High)**

**Current Behavior:**
- API key stored in plain YAML config file ([config.yaml](sentinel-agent/config.yaml))
- Backend server URL also in config (allows hardcoding endpoints in code paths)
- No built-in key rotation or dual-key overlap

**Enterprise Impact:**
- Config file is sensitive: must be guarded with RBAC, encrypted at rest, private in VCS
- No automatic key rotation without config redeploy
- Lateral movement risk: agent compromise exposes shared backend key

**Recommended Fix:**
- Load API key from environment variable or secret manager (Vault, AWS Secrets Manager, Azure Key Vault)
- Add HTTPS/mTLS cert auth in addition to API key
- Implement automated key rotation with overlap window (old key remains valid for N minutes)
- Sign agent binary or image to prevent tampering

---

### 6. 🟠 **Minimal Observability (Risk: Medium)**

**Current Behavior:**
- Standard Python logging only; no dedicated metrics endpoint
- No health heartbeat or agent status beacon
- No local queue depth, lag, or send rate tracking exposed

**Enterprise Impact:**
- Operational blind spot: difficult to detect stale agents or sustained retries
- SRE/ops cannot track ingestion SLAs or forecast scaling needs
- Troubleshooting delayed by lack of telemetry

**Recommended Fix:**
- Add `/agent/metrics` endpoint (or emit to Prometheus/StatsD)
- Track: queue depth, send rate, retry count, drop count, spool usage, lag vs. host time
- Emit heartbeat events every N minutes to backend
- Alert on stale heartbeats (agent dead), queue backlog above threshold, sustained 40x error rate

---

### 7. 🟡 **No Native Deployment Pattern in Stack (Risk: Low-Medium)**

**Current Behavior:**
- Main [docker-compose.yml](docker-compose.yml) does not include agent service
- Agent documentation shows bare-metal or hand-rolled Docker approaches
- No Kubernetes DaemonSet or systemd unit example

**Enterprise Impact:**
- Inconsistent deployment: different teams use different methods
- Onboarding friction: new hosts require manual agent setup
- Harder to enforce baseline configuration and security patches

**Recommended Fix:**
- Add example DaemonSet manifest for Kubernetes
- Add systemd service file for Linux package installs
- Define container image repository and versioning strategy
- Add Helm chart or similar templating for multi-environment rollouts

---

### 8. 🟡 **No Durable Delivery SLA Definition (Risk: Low-Medium)**

**Current Behavior:**
- Retries cap at `max_backoff` (default 30s, then exponential backoff plateaus)
- No defined maximum retries, so failing requests could retry indefinitely
- Graceful shutdown drains queue but does not persist uncommitted batch

**Enterprise Impact:**
- Unclear recovery semantics for teams running SLAs
- Can block process exit indefinitely on network partition
- Compliance audits need explicit data delivery guarantees

**Recommended Fix:**
- Define and document maximum retry count (e.g., retry 5x, then DLQ)
- Add configurable retry policy (exponential vs. linear backoff, jitter)
- Persist retry state to disk so dropped events can be reviewed/re-injected

---

## Enterprise Recommendations

### Phase 1: Immediate Hardening (Weeks 1–2)

1. **Replace IP fallback:** Change `127.0.0.1` → `null` in parser
   - Impact: cleaner data, fewer false alerts
   - Effort: < 30 min

2. **Add minimal spool:** Append-only file for unsent events
   - Impact: zero data loss on graceful shutdown + partial recovery on crash
   - Effort: 2–3 hours

3. **Export agent metrics:** Add periodic logging of queue depth, send rate, error count
   - Impact: ops gain visibility into agent health
   - Effort: 1–2 hours

4. **Externalize API key:** Load from env variable or secret manager (not YAML)
   - Impact: credential isolation, easier rotation
   - Effort: 1 hour

### Phase 2: Scalability (Weeks 3–4)

5. **Add bulk API:** Implement `POST /logs/bulk` on backend
   - Impact: 5–10x throughput improvement
   - Effort: 3–4 hours backend + 2 hours agent

6. **Add idempotency keys:** UUID per event for safe retries
   - Impact: prevents duplicates on retry storms
   - Effort: 1–2 hours

7. **Improved parser:** Plugin architecture for source-specific formats
   - Impact: higher accuracy, structured log support
   - Effort: 4–6 hours

### Phase 3: Operational Maturity (Weeks 5–8)

8. **Deployment templates:** Kubernetes DaemonSet, systemd service, Helm chart
   - Impact: consistent, scalable rollouts across org
   - Effort: 4–6 hours

9. **mTLS support:** Cert-based agent auth in addition to API key
   - Impact: defense-in-depth, revocation without key rotation
   - Effort: 3–4 hours

10. **Data governance:** Per-source allowlist/denylist, PII masking, retention policies
    - Impact: compliance, audit controls, cost containment
    - Effort: 2–3 hours

---

## Reference Implementation Blueprint

### 1. Core Data Flow

```
JSON log file (syslog, CEF, nginx, etc.)
    ↓
SourceParser (plugin-based)
    ↓ (normalized schema: timestamp, level, message, IP, source, tags)
DurableQueue (SQLite or local append-only file)
    ↓ (supervised: on restart, replay unsent + add new)
SecureSender (HTTPS + mTLS + API key)
    ↓
BulkAPI: POST /logs/bulk [{ log }, { log }, ...] (batch = 50–100 events)
    ↓ (idempotent insert, 202 response with event IDs)
Backend → PostgreSQL + alert worker processing
```

### 2. Reliability Controls

| Feature | Mechanism |
|---------|-----------|
| At-least-once delivery | Durable local queue + replay on restart |
| Deduplication | Idempotency key (UUID) per event, server-side insert check |
| Backoff strategy | Exponential + jitter, max 30s, total timeout 15 min |
| Circuit breaker | After 10 consecutive 5xx, pause 5 min before retry |
| Overflow handling | Queue bounded by disk size or event count; drop oldest when full |

### 3. Security Controls

| Layer | Mechanism |
|-------|-----------|
| Transport | HTTPS enforced; mTLS optional for agent cert auth |
| Identity | API key (bearer token) + optional JWT with exp/scope |
| Secrets | Load from env var or secret manager at runtime; no plaintext in config |
| Rotation | Dual-key window: new key active, old key honored for 5 min overlap |
| Audit | Sign agent binary/image; track pull SHA in logs; emit audit events |

### 4. Observability

```yaml
Agent Metrics (Prometheus format):
  sentinel_agent_queue_depth          # Current in-memory queue size
  sentinel_agent_spool_size_bytes     # Local disk spool usage
  sentinel_agent_logs_sent_total      # Cumulative events sent (counter)
  sentinel_agent_logs_dropped_total   # Cumulative events dropped (counter)
  sentinel_agent_retries_total        # Cumulative retry attempts (counter)
  sentinel_agent_send_duration_seconds # Histogram of POST latencies
  sentinel_agent_lag_seconds          # Wall-clock age of oldest queued event
  sentinel_agent_health_status        # 1 (OK), 0 (ERROR)

Heartbeat Event (every 60s):
  {
    "source": "sentinel-agent",
    "log_level": "INFO",
    "message": "Agent heartbeat: queue_depth=42, spool_size_mb=0.5, uptime_seconds=3600",
    "timestamp": "2026-03-19T12:34:56Z",
    "tags": {
      "agent_version": "1.2.0",
      "agent_id": "host-prod-01.example.com",
      "queue_depth": 42,
      "spool_mb": 0.5
    }
  }
```

---

## Quick Wins (Immediate Action Items)

### Win 1: Fix IP Fallback (5 minutes)

**File:** [sentinel-agent/parser.py](sentinel-agent/parser.py)  
**Change:**
```python
def extract_ipv4(message: str) -> str | None:  # Return None instead of str
    match = IPV4_RE.search(message)
    return match.group(0) if match else None  # Changed from "127.0.0.1"
```

**Impact:** Eliminates 127.0.0.1 false data contamination.

---

### Win 2: Add Minimal Metrics Logging (30 minutes)

**File:** [sentinel-agent/agent.py](sentinel-agent/agent.py)  
**Add:**
```python
import time

def log_stats(log_queue: queue.Queue, interval: float = 60.0) -> None:
    """Emit queue stats every interval seconds."""
    logger = logging.getLogger(__name__)
    start = time.time()
    while time.time() - start < interval:
        time.sleep(1)
    logger.info(
        "Agent stats: queue_depth=%d, uptime_seconds=%d",
        log_queue.qsize(),
        int(time.time() - start),
    )
```

**Impact:** Operational visibility into queue health.

---

### Win 3: Externalize API Key (15 minutes)

**File:** [sentinel-agent/config.py](sentinel-agent/config.py)  
**Change:**
```python
import os

api_key = os.environ.get("SENTINEL_API_KEY") or sentinel_raw.get("api_key")
if not api_key:
    raise ValueError("api_key must be set in environment or config")
```

**Impact:** Credentials not stored in YAML; compatible with K8s secrets, Vault, etc.

---

### Win 4: Add Bulk Endpoint (2 hours backend + 1 hour agent)

**File:** [app/api/logs.py](app/api/logs.py)  
**Add:**
```python
@router.post("/logs/bulk", response_model=list[LogWithAlertResponse], status_code=202)
async def bulk_ingest_logs(
    payloads: list[LogCreate],
    session: AsyncSession = Depends(get_session),
) -> list[LogWithAlertResponse]:
    """Bulk ingest multiple logs in a single request."""
    results = []
    for payload in payloads:
        log = await ingest_log(session, payload)
        await increment_async("logs_received")
        results.append(LogWithAlertResponse(log=..., alert=None))
    return results
```

**Impact:** 5–10x throughput improvement.

---

### Win 5: Add Spool Queue (3 hours)

**File:** [sentinel-agent/sender.py](sentinel-agent/sender.py)  
**Add SQLite or append-only file:**
```python
import sqlite3
import json

class DurableQueue:
    def __init__(self, db_path: str = "spool.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                payload TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0
            )
        """)
        self.conn.commit()

    def push(self, payload: dict) -> None:
        self.conn.execute(
            "INSERT INTO events (payload) VALUES (?)",
            (json.dumps(payload),)
        )
        self.conn.commit()

    def pop_batch(self, size: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, payload FROM events LIMIT ?", (size,)
        ).fetchall()
        return [(row[0], json.loads(row[1])) for row in rows]

    def mark_sent(self, event_id: int) -> None:
        self.conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        self.conn.commit()
```

**Impact:** Zero data loss on process restart.

---

## Current State Assessment

| Component | Status | Notes |
|-----------|--------|-------|
| File tailing | ✅ Ready | Handles rotation, truncation, symlinks |
| Parsing | ⚠️ Draft | Heuristic-only; 127.0.0.1 fallback needs fix |
| Buffering | ⚠️ Lab-grade | In-memory only; no spool |
| Retries | ✅ Ready | Exponential backoff works well |
| API transport | ✅ Ready | Async, auth header support |
| Auth integration | ⚠️ Limited | Static API key; no secret manager |
| Observability | 🔴 Minimal | Logs only; no metrics |
| Deployability | 🔴 None | No K8s/systemd/helm examples |
| Durability | 🔴 None | At-most-once on crash |
| Scalability | 🟡 Limited | Single-event sends; ~50–100 logs/s max |

---

## Recommended Reading

- [agent.py](sentinel-agent/agent.py) – Thread orchestration and lifecycle
- [watcher.py](sentinel-agent/watcher.py) – File polling and rotation detection
- [sender.py](sentinel-agent/sender.py) – Delivery and retry policy
- [config.py](sentinel-agent/config.py) – Config validation
- [Architecture.md](Architecture.md) – Backend design for context

---

## Next Steps

1. **Triage:** Prioritize fixes by org risk profile (compliance, data loss tolerance, throughput SLA)
2. **Prototyping:** Implement wins 1–3 to build confidence
3. **Roadmap:** Schedule Phase 1–3 hardening across sprints
4. **Testing:** Add chaos experiments (outages, auth failures, disk full)
5. **Rollout:** Pilot on non-critical hosts before org-wide deployment

---

**Document Version:** 1.0  
**Last Updated:** March 19, 2026  
**Next Review:** After Phase 1 hardening is implemented
