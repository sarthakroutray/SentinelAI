# SentinelAI Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        HOST SYSTEMS                              │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐ │
│  │  App Logs        │ │  Firewall Logs   │ │  System Logs     │ │
│  └────────┬─────────┘ └────────┬─────────┘ └────────┬─────────┘ │
└───────────┼──────────────────────┼──────────────────────┼─────────┘
           │                      │                      │
           │ (Optional)           │ (Optional)           │ (Optional)
           v                      v                      v
      ┌────────────────────────────────────────────────────────┐
      │        Sentinel Agent (File Tailing)                   │
      │  Tails local files → forwards to /logs                 │
      └───────────────────┬──────────────────────────────────┘
                          │
                          v
      ┌────────────────────────────────────────────────────────┐
      │       FastAPI Backend (app/main.py)                    │
      │  ┌──────────────────────────────────────────────────┐  │
      │  │  POST /logs          - Ingest log event          │  │
      │  │  GET /alerts         - Retrieve alerts (paginated)│ │
      │  │  GET /metrics        - Current statistics        │  │
      │  │  GET /health         - System status             │  │
      │  │  WS /ws/dashboard    - Real-time stream          │  │
      │  └──────────────────────────────────────────────────┘  │
      │              │                                           │
      │              v                                           │
      │    ┌─────────────────┐                                  │
      │    │ Redis Queue     │                                  │
      │    │ (Message Broker)│                                  │
      │    └────────┬────────┘                                  │
      │             │                                            │
      └─────────────┼────────────────────────────────────────────┘
                    │
                    v
      ┌────────────────────────────────────────────────────────┐
      │        Alert Worker (app/workers/alert_worker.py)      │
      │                                                         │
      │  ┌─ Processing Pipeline ─────────────────────────────┐ │
      │  │                                                    │ │
      │  │  1. Dequeue log from Redis                        │ │
      │  │                                                    │ │
      │  │  2. Classify via Rule Engine                      │ │
      │  │     - High-signal events (auth failures, etc.)   │ │
      │  │     - IP burst detection (>5 errors in 60s)      │ │
      │  │     → If match: severity=HIGH, skip other checks │ │
      │  │                                                    │ │
      │  │  3. Statistical Scoring (if not HIGH)             │ │
      │  │     - Compare against baseline of IP              │ │
      │  │     - Check error ratio vs historical average    │ │
      │  │     → Score: 0–1 (0=normal, 1=anomalous)         │ │
      │  │                                                    │ │
      │  │  4. Isolation Forest (if not HIGH)                │ │
      │  │     - 100 trees trained on baseline behaviors     │ │
      │  │     - Detect multi-dimensional anomalies         │ │
      │  │     → Score: 0–1                                  │ │
      │  │                                                    │ │
      │  │  5. Combine Scores                                │ │
      │  │     - Weighted average: 0.5*rule + 0.3*stat...   │ │
      │  │     - Final: max(combined, high_penalty)         │ │
      │  │     - Discretize to severity: HIGH/MED/LOW        │ │
      │  │                                                    │ │
      │  │  6. Persist Alert                                 │ │
      │  │     → Insert into PostgreSQL                      │ │
      │  │     → Publish to Redis Pub/Sub                    │ │
      │  │                                                    │ │
      │  │  7. Update IP Profile                             │ │
      │  │     - Increment error count if log_level=ERROR   │ │
      │  │     - Update last_seen timestamp                 │ │
      │  │                                                    │ │
      │  └────────────────────────────────────────────────────┘ │
      │                                                         │
      └─────────────────────────────────────────────────────────┘
                    │
                    v
      ┌────────────────────────────────────────────────────────┐
      │        PostgreSQL Database                             │
      │  ┌──────────────┐  ┌──────────────┐ ┌──────────────┐  │
      │  │   logs       │  │   alerts     │ │ ip_profiles  │  │
      │  │ (raw events) │  │ (detections) │ │ (per-IP stats)   │
      │  └──────────────┘  └──────────────┘ └──────────────┘  │
      └────────────────────────────────────────────────────────┘
                    │
                    └─ Pub/Sub ─────┐
                                    v
      ┌────────────────────────────────────────────────────────┐
      │        Next.js Dashboard (sentinel-frontend)           │
      │  ┌──────────────────────────────────────────────────┐  │
      │  │  Real-Time Components (WebSocket-fed)             │  │
      │  │  • Alert Table           - New alerts streamed   │  │
      │  │  • Metrics Cards         - Counts updated 5s     │  │
      │  │  • System Health Status  - Worker state, DB lag  │  │
      │  │  • Throughput Chart      - Logs/alerts over time │  │
      │  │  • Queue Status          - Processing depth      │  │
      │  │                                                    │  │
      │  │  REST-Polled Components                           │  │
      │  │  • IP Profiles (on-demand)                        │  │
      │  │  • Historical Timeseries (10s poll)               │  │
      │  │  • DLQ Visibility (health checks)                 │  │
      │  └──────────────────────────────────────────────────┘  │
      └────────────────────────────────────────────────────────┘
```

---

## 🔄 Message Flow (End-to-End)

### 1. Log Ingestion
```
POST /logs → FastAPI validation → Redis enqueue → Immediate 202 response
```

### 2. Alert Worker Processing
```
Redis dequeue → Rule check → ML scoring → Aggregate → Persist → Pub/Sub broadcast
```

### 3. Dashboard Update
```
WebSocket connection → Listen on Pub/Sub → Forward new alert/metrics → Render in real-time
```

---

## 🧠 Anomaly Scoring (Hybrid Model)

### Phase 1: Rule Engine
**Input:** Log event  
**Output:** Severity + score (or pass to Phase 2)

Rules:
- **High-Signal Events**: Exact message/level matches (auth failures, etc.)
- **IP Burst**: 5+ errors from same IP within 60 seconds

### Phase 2: Statistical Baseline
**Input:** Log event + IP profile  
**Output:** 0–1 score

- Compare IP's error ratio to historical mean
- Use Z-score to detect deviation
- Score formula: `(current_ratio - mean_ratio) / std_dev`

### Phase 3: Isolation Forest
**Input:** Multidimensional log features  
**Output:** 0–1 anomaly score

- Train on baseline logs (ingested at startup)
- Detect rare combinations of (log_level, source, message patterns, IP)
- Isolation depth approach: more isolated = more anomalous

### Final Scoring
```
combined_score = 0.5 * rule_score + 0.3 * stat_score + 0.2 * iso_score

if rule_severity == HIGH:
    final_score = max(combined_score, 0.9)  # Enforce severity
else:
    final_score = combined_score

severity = {
    final_score >= 0.7  → HIGH
    final_score >= 0.4  → MEDIUM
    otherwise           → LOW
}
```

---

## 📊 Data Models

### Log (ORM Model)
```python
class Log(Base):
    id: str
    source: str
    log_level: str
    message: str
    timestamp: datetime
    ip_address: str | None
    created_at: datetime
```

### Alert (ORM Model)
```python
class Alert(Base):
    id: str
    log_id: str
    severity: str  # HIGH, MEDIUM, LOW
    risk_score: float  # 0–1
    reason: str  # Rule match explanation
    score_breakdown: dict  # {rule: 0.9, statistical: 0.2, isolation: 0.1}
    anomaly_type: str | None
    created_at: datetime
    log: Log  # Relationship
```

### IP Profile (Cache in Memory)
```python
class IPProfile:
    ip: str
    total_logs: int
    error_count: int
    error_ratio: float  # error_count / total_logs
    last_seen: datetime
    avg_risk_score: float  # Moving average of alert scores
    recent_alert_count: int  # Alerts in last 24h
```

---

## 🔄 Queue Architecture

### Main Queue
- Incoming logs awaiting processing
- FIFO (First In, First Out)
- Durable (persists across crashes)

### Processing Queue
- Logs actively being evaluated
- Timeout: 30 seconds
- Auto-requeue if stale

### Dead-Letter Queue (DLQ)
- Logs that fail after max retries
- Retained for inspection / debugging
- Manual recovery possible via `/dlq` endpoint

### Worker Recovery
- On startup: sweep unenqueued logs, requeue older than 30s
- Auto-remove old DLQ items (default: 72 hours)

---

## 🔐 Database Considerations

### Single-Worker Constraint
- **Why**: In-memory baseline matrices not shared across workers
- **Solution**: Either keep `replicas=1`, or migrate state to Redis cache

### Schema
- Indexes on `(alerts.severity, alerts.created_at)` for fast paginated queries
- Partition logs by month if exceeding 10M rows

### Performance
- Async SQLAlchemy for non-blocking DB calls
- Connection pooling (10 base + 20 overflow)
- Read replicas optional at scale

---

## 📝 Logging & Observability

### Levels
- **INFO**: Major milestones (worker startup, model retrain)
- **WARNING**: Recoverable issues (DLQ items, queue backlog)
- **ERROR**: Critical failures (DB loss, Redis unavailable)

### Metrics Exposed
- `logs_received`: Total logs ingested
- `alerts_created`: Alerts generated
- `queue_depth`: Backlog size
- `dlq_count`: Failed messages
- `retries`: Auto-retry attempts
- `high_risk_count`, `medium_risk_count`, `low_risk_count`

---

## 🚀 Scalability & Limitations

### Current Limitations
1. **Single worker**: In-memory state not shared
2. **No horizontal replication**: One copy of models
3. **Memory growth**: Baseline cache unbounded

### Next Steps for Scale
1. **Shared state**: Redis-backed caches for profiles, baselines
2. **Horizontal workers**: Each worker subscribes to queue
3. **Model distribution**: S3/object storage for trained models
4. **Time-series DB**: ClickHouse/TimescaleDB for metrics

---

## 📚 Related Files
- [app/workers/alert_worker.py](app/workers/alert_worker.py) – Main processing loop
- [app/services/scoring_engine.py](app/services/scoring_engine.py) – Hybrid scoring
- [app/services/rule_engine.py](app/services/rule_engine.py) – Rules
- [docker-compose.yml](docker-compose.yml) – Infrastructure as code

