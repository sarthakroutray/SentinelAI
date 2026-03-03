"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  Alert,
  AlertSortOption,
  HealthStatus,
  Metrics,
  MetricsTimeseries,
  Queues,
} from "@/lib/api";
import {
  fetchAlerts,
  fetchHealth,
  fetchMetricsTimeseries,
  fetchQueues,
} from "@/lib/api";
import MetricsCards from "@/components/MetricsCards";
import QueueStatus from "@/components/QueueStatus";
import AlertTable from "@/components/AlertTable";
import AlertModal from "@/components/AlertModal";
import ThroughputChart from "@/components/ThroughputChart";
import SystemHealthPanel from "@/components/SystemHealthPanel";
import { useDashboardWebSocket } from "@/lib/useDashboardWebSocket";
import ErrorBoundary from "@/components/ErrorBoundary";

const POLL_INTERVAL = 5_000;
const CHART_POLL_INTERVAL = 10_000;
const DEFAULT_PAGE_SIZE = 50;

export default function DashboardPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize] = useState(DEFAULT_PAGE_SIZE);
  const [sortOption, setSortOption] = useState<AlertSortOption>("timestamp_desc");
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [queues, setQueues] = useState<Queues | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshingAlerts, setIsRefreshingAlerts] = useState(false);
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [timeseries, setTimeseries] = useState<MetricsTimeseries>({
    timestamps: [],
    logs: [],
    alerts: [],
  });
  const [health, setHealth] = useState<HealthStatus | null>(null);

  const offset = (currentPage - 1) * pageSize;

  const showingRange = useMemo(() => {
    if (total === 0 || alerts.length === 0) {
      return { start: 0, end: 0 };
    }
    const start = offset + 1;
    const end = Math.min(offset + alerts.length, total);
    return { start, end };
  }, [alerts.length, offset, total]);

  const canGoPrev = currentPage > 1;
  const canGoNext = offset + alerts.length < total;

  const handleAlertMessage = useCallback((incomingAlert: Alert) => {
    if (sortOption === "timestamp_desc" && currentPage === 1) {
      setAlerts((previousAlerts) => {
        if (previousAlerts.some((item) => item.id === incomingAlert.id)) {
          return previousAlerts;
        }
        return [incomingAlert, ...previousAlerts].slice(0, pageSize);
      });
    }

    setTotal((previousTotal) => previousTotal + 1);
  }, [currentPage, pageSize, sortOption]);

  const handleMetricsMessage = useCallback((incomingMetrics: Metrics) => {
    setMetrics(incomingMetrics);
  }, []);

  useDashboardWebSocket({
    onAlert: handleAlertMessage,
    onMetrics: handleMetricsMessage,
  });

  useEffect(() => {
    let cancelled = false;

    const fetchAlertPage = async () => {
      try {
        setIsRefreshingAlerts(true);
        const a = await Promise.allSettled([
          fetchAlerts({
            limit: pageSize,
            offset,
            sort: sortOption,
          }),
        ]);

        if (cancelled) return;

        if (a[0].status === "fulfilled") {
          setAlerts(a[0].value.items);
          setTotal(a[0].value.total);
        }

        if (a[0].status === "fulfilled") setError(null);
        else setError("Alert API call failed");

        setLastUpdated(new Date());
      } catch {
        if (!cancelled) setError("Network error");
      } finally {
        if (!cancelled) setIsRefreshingAlerts(false);
      }
    };

    fetchAlertPage();
    const pollId = setInterval(fetchAlertPage, 30_000);

    return () => {
      cancelled = true;
      clearInterval(pollId);
    };
  }, [offset, pageSize, sortOption]);

  useEffect(() => {
    let cancelled = false;

    const pollQueues = async () => {
      const queueResult = await Promise.allSettled([fetchQueues()]);
      if (cancelled) return;

      if (queueResult[0].status === "fulfilled") {
        setQueues(queueResult[0].value);
      }
    };

    pollQueues();
    const id = setInterval(pollQueues, POLL_INTERVAL);

    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const pollChartAndHealth = async () => {
      const [series, healthStatus] = await Promise.allSettled([
        fetchMetricsTimeseries(15),
        fetchHealth(),
      ]);

      if (cancelled) return;

      if (series.status === "fulfilled") setTimeseries(series.value);
      if (healthStatus.status === "fulfilled") setHealth(healthStatus.value);
    };

    pollChartAndHealth();
    const id = setInterval(pollChartAndHealth, CHART_POLL_INTERVAL);

    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    setCurrentPage(1);
  }, [sortOption]);

  useEffect(() => {
    if (total > 0 && offset >= total) {
      setCurrentPage(Math.max(1, Math.ceil(total / pageSize)));
    }
  }, [offset, pageSize, total]);

  return (
    <div className="mx-auto max-w-7xl space-y-8">
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-zinc-200">SentinelAI Dashboard v1</p>
            <p className="text-xs text-zinc-500">Realtime security analytics and anomaly monitoring</p>
          </div>
          <span className="rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-zinc-300">
            Production UI v1
          </span>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Section: Metrics */}
      <ErrorBoundary section="Metrics">
        <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
          <SectionHeader title="Metrics" updated={lastUpdated} />
          <MetricsCards metrics={metrics} />
        </section>
      </ErrorBoundary>

      <ErrorBoundary section="Throughput">
        <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
          <SectionHeader title="Throughput" />
          <ThroughputChart
            timestamps={timeseries.timestamps}
            logs={timeseries.logs}
            alerts={timeseries.alerts}
          />
        </section>
      </ErrorBoundary>

      <ErrorBoundary section="System Health">
        <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
          <SectionHeader title="System Health" />
          <SystemHealthPanel health={health} />
        </section>
      </ErrorBoundary>

      {/* Section: Queue Status */}
      <ErrorBoundary section="Queue Status">
        <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
          <SectionHeader title="Queue Status" />
          <QueueStatus queues={queues} />
        </section>
      </ErrorBoundary>

      {/* Section: Alerts */}
      <ErrorBoundary section="Alerts">
        <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
        <SectionHeader
          title="Alerts"
          subtitle={`Showing ${showingRange.start}–${showingRange.end} of ${total} alerts`}
        />

        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <label className="flex items-center gap-2 text-xs text-zinc-400">
            <span>Sort</span>
            <select
              value={sortOption}
              onChange={(event) => setSortOption(event.target.value as AlertSortOption)}
              className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-200 outline-none transition-colors focus:border-zinc-500"
            >
              <option value="timestamp_desc">Newest First</option>
              <option value="timestamp_asc">Oldest First</option>
              <option value="risk_score_desc">Highest Risk</option>
              <option value="risk_score_asc">Lowest Risk</option>
            </select>
          </label>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
              disabled={!canGoPrev}
              className="rounded-md border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-xs text-zinc-200 transition-colors enabled:hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Previous
            </button>
            <button
              type="button"
              onClick={() => setCurrentPage((page) => page + 1)}
              disabled={!canGoNext}
              className="rounded-md border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-xs text-zinc-200 transition-colors enabled:hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>

        <AlertTable
          alerts={alerts}
          isRefreshing={isRefreshingAlerts}
          onAlertClick={setSelectedAlert}
        />
      </section>      </ErrorBoundary>
      <AlertModal
        alert={selectedAlert}
        isOpen={selectedAlert !== null}
        onClose={() => setSelectedAlert(null)}
      />
    </div>
  );
}

/* ── Sub-component ─────────────────────────────────────────────────── */

function SectionHeader({
  title,
  subtitle,
  updated,
}: {
  title: string;
  subtitle?: string;
  updated?: Date | null;
}) {
  return (
    <div className="mb-3 flex items-end justify-between">
      <div>
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold text-zinc-200">{title}</h2>
          <span className="rounded border border-zinc-700 bg-zinc-950 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-300">
            v1
          </span>
        </div>
        {subtitle && (
          <p className="text-xs text-zinc-500">{subtitle}</p>
        )}
      </div>
      {updated && (
        <span className="text-xs tabular-nums text-zinc-500">
          Updated {updated.toLocaleTimeString()}
        </span>
      )}
    </div>
  );
}
