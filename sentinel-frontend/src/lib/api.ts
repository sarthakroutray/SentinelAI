const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

/* ── Types ─────────────────────────────────────────────────────────── */

export interface Alert {
  id: string;
  log_id: string;
  severity: "HIGH" | "MEDIUM" | "LOW";
  reason: string;
  risk_score: number;
  score_breakdown: Record<string, number>;
  anomaly_type: string | null;
  created_at: string;
  log?: {
    id: string;
    source: string;
    log_level: string;
    message: string;
    ip_address: string | null;
    timestamp: string;
  };
}

export type AlertSortOption =
  | "timestamp_desc"
  | "timestamp_asc"
  | "risk_score_desc"
  | "risk_score_asc";

export interface AlertsPage {
  total: number;
  limit: number;
  offset: number;
  items: Alert[];
}

export interface Metrics {
  logs_received: number;
  alerts_created: number;
  retries: number;
  dlq_count: number;
  high_risk_count: number;
  medium_risk_count: number;
  low_risk_count: number;
  [key: string]: number;
}

export interface Queues {
  main: number;
  processing: number;
  dlq: number;
}

export interface MetricsTimeseries {
  timestamps: string[];
  logs: number[];
  alerts: number[];
}

export interface HealthStatus {
  status: "ok";
  db_latency_ms: number;
  worker_alive: boolean;
  queue_depth: number;
  last_model_retrain: string | null;
}

export interface IpProfile {
  ip: string;
  total_logs: number;
  error_ratio: number;
  last_seen: string;
  avg_risk_score: number;
  recent_alert_count: number;
}

/* ── Fetchers ──────────────────────────────────────────────────────── */

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${path} returned ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchAlerts(params?: {
  limit?: number;
  offset?: number;
  sort?: AlertSortOption;
}): Promise<AlertsPage> {
  const query = new URLSearchParams();
  if (params?.limit !== undefined) query.set("limit", String(params.limit));
  if (params?.offset !== undefined) query.set("offset", String(params.offset));
  if (params?.sort !== undefined) query.set("sort", params.sort);
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return get<AlertsPage>(`/alerts${suffix}`);
}

export async function fetchMetrics(): Promise<Metrics> {
  return get<Metrics>("/metrics");
}

export async function fetchQueues(): Promise<Queues> {
  return get<Queues>("/queues");
}

export async function fetchIpProfile(ip: string): Promise<IpProfile | null> {
  const res = await fetch(`${API_BASE}/ip/${encodeURIComponent(ip)}/profile`, {
    cache: "no-store",
  });

  if (res.status === 404) {
    return null;
  }

  if (!res.ok) {
    throw new Error(`API /ip/${ip}/profile returned ${res.status}`);
  }

  return (await res.json()) as IpProfile;
}

export async function fetchMetricsTimeseries(window = 15): Promise<MetricsTimeseries> {
  return get<MetricsTimeseries>(`/metrics/timeseries?window=${window}`);
}

export async function fetchHealth(): Promise<HealthStatus> {
  return get<HealthStatus>("/health");
}
