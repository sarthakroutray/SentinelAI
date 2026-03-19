# SentinelAI API Reference

## Base URL
```
http://localhost:8000
https://api.sentinelai.example.com  # Production
```

## Authentication
Optional `X-API-Key` header (if `API_KEY` is set in `.env`):
```bash
curl -H "X-API-Key: your-secret-key" http://localhost:8000/alerts
```

---

## 📥 Log Ingestion

### POST /logs
Ingest a log event for async processing.

**Request:**
```bash
curl -X POST http://localhost:8000/logs \
  -H "Content-Type: application/json" \
  -d '{
    "source": "firewall",
    "log_level": "ERROR",
    "message": "Unauthorized access attempt from 192.168.1.50",
    "timestamp": "2026-03-20T12:34:56Z",
    "ip_address": "192.168.1.50"
  }'
```

**Response:** `202 Accepted`
```json
{}
```

**Fields:**
| Field | Type | Required | Example |
|-------|------|----------|---------|
| source | string | Yes | "firewall", "app", "os" |
| log_level | string | Yes | "ERROR", "WARN", "INFO" |
| message | string | Yes | "Unauthorized access" |
| timestamp | ISO 8601 | Yes | "2026-03-20T12:34:56Z" |
| ip_address | string | No | "192.168.1.1" |

---

## 📤 Alerts

### GET /alerts
Fetch alerts with pagination and filtering.

**Request:**
```bash
curl "http://localhost:8000/alerts?limit=50&offset=0&sort=timestamp_desc&severity=HIGH"
```

**Query Parameters:**
| Param | Type | Default | Values |
|-------|------|---------|--------|
| limit | int | 50 | 1–200 |
| offset | int | 0 | >= 0 |
| sort | string | timestamp_desc | `timestamp_desc`, `timestamp_asc`, `risk_score_desc`, `risk_score_asc` |
| severity | string | (none) | `HIGH`, `MEDIUM`, `LOW` |

**Response:** `200 OK`
```json
{
  "total": 245,
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "id": "alert-uuid-1",
      "log_id": "log-uuid-1",
      "severity": "HIGH",
      "reason": "IP burst detected: 6 errors in 60s",
      "risk_score": 0.89,
      "score_breakdown": {
        "rule": 0.9,
        "statistical": 0.2,
        "isolation": 0.1
      },
      "anomaly_type": "ip_burst+error_rate",
      "created_at": "2026-03-20T12:34:56Z",
      "log": {
        "id": "log-uuid-1",
        "source": "firewall",
        "log_level": "ERROR",
        "message": "Unauthorized access",
        "ip_address": "192.168.1.50",
        "timestamp": "2026-03-20T12:34:50Z"
      }
    }
  ]
}
```

---

## 📊 Metrics

### GET /metrics
Get current system metrics.

**Request:**
```bash
curl http://localhost:8000/metrics
```

**Response:** `200 OK`
```json
{
  "logs_received": 5432,
  "alerts_created": 128,
  "retries": 12,
  "dlq_count": 2,
  "enqueue_failures": 1,
  "high_risk_count": 45,
  "medium_risk_count": 56,
  "low_risk_count": 27
}
```

### GET /metrics/timeseries
Get metrics over a time window.

**Request:**
```bash
curl "http://localhost:8000/metrics/timeseries?window=15"
```

**Query Parameters:**
| Param | Type | Default | Values |
|-------|------|---------|--------|
| window | int | 15 | 5, 15, 30, 60 (minutes) |

**Response:** `200 OK`
```json
{
  "timestamps": [
    "2026-03-20T12:30:00Z",
    "2026-03-20T12:31:00Z",
    "2026-03-20T12:32:00Z"
  ],
  "logs": [120, 115, 130],
  "alerts": [5, 3, 8]
}
```

---

## 🏥 Health & Status

### GET /health
Get system health status.

**Request:**
```bash
curl http://localhost:8000/health
```

**Response:** `200 OK`
```json
{
  "status": "ok",
  "db_latency_ms": 3.45,
  "worker_alive": true,
  "queue_depth": 12,
  "last_model_retrain": "2026-03-20T10:00:00Z"
}
```

### GET /queues
Get queue statistics.

**Request:**
```bash
curl http://localhost:8000/queues
```

**Response:** `200 OK`
```json
{
  "main": 12,
  "processing": 3,
  "dlq": 0
}
```

---

## 👤 IP Profiles

### GET /ip/{ip}/profile
Get enriched profile for an IP address.

**Request:**
```bash
curl http://localhost:8000/ip/192.168.1.50/profile
```

**Response:** `200 OK` (if found)
```json
{
  "ip": "192.168.1.50",
  "total_logs": 256,
  "error_ratio": 0.35,
  "last_seen": "2026-03-20T12:34:56Z",
  "avg_risk_score": 0.42,
  "recent_alert_count": 7
}
```

**Response:** `404 Not Found` (if no profile exists)
```json
null
```

---

## 🔌 Real-Time WebSocket

### WS /ws/dashboard
Subscribe to real-time alerts and metrics.

**Connect:**
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/dashboard');

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  console.log(msg.type, msg.payload);
};

ws.onerror = (err) => console.error('WebSocket error:', err);
ws.onclose = () => console.log('Disconnected');
```

**Message Types:**

#### 1. Alert Message
Sent when a new alert is generated.
```json
{
  "type": "alert",
  "payload": {
    "id": "alert-uuid",
    "log_id": "log-uuid",
    "severity": "HIGH",
    "risk_score": 0.89,
    "reason": "IP burst detected",
    "created_at": "2026-03-20T12:34:56Z"
  }
}
```

#### 2. Metrics Message
Broadcast every 5 seconds.
```json
{
  "type": "metrics",
  "payload": {
    "logs_received": 5432,
    "alerts_created": 128,
    "high_risk_count": 45,
    "medium_risk_count": 56,
    "low_risk_count": 27,
    "queue_depth": 12
  }
}
```

**Reconnection:** Client automatically reconnects on disconnect (exponential backoff, max 30s).

---

## ❌ Error Responses

All endpoints return appropriate HTTP status codes:

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 202 | Accepted (async processing) |
| 400 | Bad request (validation error) |
| 401 | Unauthorized (missing/invalid API key) |
| 404 | Not found |
| 500 | Server error |

**Error Response Format:**
```json
{
  "detail": "Description of the error"
}
```

---

## 🔄 Rate Limiting

Currently **not enforced**, but plan for:
- 1000 requests/minute per API key
- 100 requests/minute per IP (unauthenticated)

---

## 📈 Best Practices

1. **Batch Logging**: Send logs in small batches for efficiency
2. **Cache IP Profiles**: Don't poll the same IP every request
3. **WebSocket over Polling**: Use WebSocket for real-time updates
4. **Pagination**: Use limit/offset for large result sets
5. **Error Handling**: Implement exponential backoff for retries

---

## 🧪 Testing

### Quick Test
```bash
# 1. Ingest a log
curl -X POST http://localhost:8000/logs \
  -H "Content-Type: application/json" \
  -d '{"source":"test","log_level":"ERROR","message":"Test","timestamp":"2026-03-20T12:00:00Z","ip_address":"192.168.1.1"}'

# 2. Check metrics
curl http://localhost:8000/metrics

# 3. Retrieve alerts
curl http://localhost:8000/alerts

# 4. Health check
curl http://localhost:8000/health
```

---

## 📝 Changelog

See [CHANGELOG.md](CHANGELOG.md) for API version history and breaking changes.

