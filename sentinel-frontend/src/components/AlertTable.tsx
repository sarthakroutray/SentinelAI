import type { Alert } from "@/lib/api";
import RiskBadge from "./RiskBadge";

interface AlertTableProps {
  alerts: Alert[];
  isRefreshing?: boolean;
  onAlertClick?: (alert: Alert) => void;
}

export default function AlertTable({
  alerts,
  isRefreshing = false,
  onAlertClick,
}: AlertTableProps) {
  if (alerts.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900/90 text-sm text-zinc-500">
        No alerts yet
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-900/70">
      <div className="flex items-center justify-between border-b border-zinc-800/80 bg-zinc-950/60 px-4 py-1 text-xs text-zinc-500">
        <span className="font-medium uppercase tracking-wide">Alerts Table · v1</span>
        <span>{isRefreshing ? "Refreshing…" : ""}</span>
      </div>
      <table className="w-full text-left text-sm">
        <thead className="border-b border-zinc-800 bg-zinc-900/70 text-xs uppercase tracking-wider text-zinc-500">
          <tr>
            <th className="px-4 py-3">Timestamp</th>
            <th className="px-4 py-3">IP</th>
            <th className="px-4 py-3">Severity</th>
            <th className="px-4 py-3">Risk Score</th>
            <th className="px-4 py-3">Anomaly Type</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/60">
          {alerts.map((alert) => (
            <tr
              key={alert.id}
              onClick={() => onAlertClick?.(alert)}
              className="cursor-pointer bg-zinc-900 transition-colors hover:bg-zinc-800/50"
            >
              {/* Timestamp */}
              <td className="whitespace-nowrap px-4 py-3 text-zinc-400">
                {formatTimestamp(alert.created_at)}
              </td>

              {/* IP */}
              <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-zinc-300">
                {alert.log?.ip_address ?? "—"}
              </td>

              {/* Severity */}
              <td className="px-4 py-3">
                <RiskBadge severity={alert.severity} />
              </td>

              {/* Risk Score + Bar */}
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="w-10 text-right font-mono text-xs tabular-nums text-zinc-300">
                    {alert.risk_score.toFixed(2)}
                  </span>
                  <div className="h-1.5 w-24 overflow-hidden rounded-full bg-zinc-800">
                    <div
                      className={`h-full rounded-full transition-all ${riskBarColor(alert.risk_score)}`}
                      style={{ width: `${Math.min(alert.risk_score * 100, 100)}%` }}
                    />
                  </div>
                </div>
              </td>

              {/* Anomaly Type */}
              <td className="px-4 py-3 text-xs text-zinc-400">
                {alert.anomaly_type
                  ? alert.anomaly_type.replace(/\+/g, " · ")
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Helpers ───────────────────────────────────────────────────────── */

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  } catch {
    return iso;
  }
}

function riskBarColor(score: number): string {
  if (score >= 0.7) return "bg-red-500";
  if (score >= 0.4) return "bg-yellow-400";
  if (score >= 0.2) return "bg-blue-400";
  return "bg-zinc-600";
}
