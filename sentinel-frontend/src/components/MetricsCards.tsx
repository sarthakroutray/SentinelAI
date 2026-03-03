import type { Metrics } from "@/lib/api";

interface MetricsCardsProps {
  metrics: Metrics | null;
}

const cards: { key: keyof Metrics; label: string; accent: string }[] = [
  { key: "logs_received", label: "Logs Received", accent: "text-emerald-400" },
  { key: "alerts_created", label: "Alerts Created", accent: "text-red-400" },
  { key: "retries", label: "Retries", accent: "text-yellow-400" },
  { key: "dlq_count", label: "DLQ Count", accent: "text-orange-400" },
];

export default function MetricsCards({ metrics }: MetricsCardsProps) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map(({ key, label, accent }) => (
        <div
          key={key}
          className="rounded-lg border border-zinc-800 bg-zinc-900/90 p-5"
        >
          <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
            {label}
          </p>
          <p className={`mt-2 text-3xl font-bold tabular-nums ${accent}`}>
            {metrics ? metrics[key].toLocaleString() : "—"}
          </p>
        </div>
      ))}

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/90 p-5 sm:col-span-2 lg:col-span-4">
        <div className="flex items-center gap-2">
          <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
            Severity Distribution
          </p>
          <span className="rounded border border-zinc-700 bg-zinc-950 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-300">
            v1
          </span>
        </div>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <SeverityItem
            label="HIGH"
            value={metrics?.high_risk_count}
            accent="text-red-400"
          />
          <SeverityItem
            label="MEDIUM"
            value={metrics?.medium_risk_count}
            accent="text-yellow-400"
          />
          <SeverityItem
            label="LOW"
            value={metrics?.low_risk_count}
            accent="text-blue-400"
          />
        </div>
      </div>
    </div>
  );
}

function SeverityItem({
  label,
  value,
  accent,
}: {
  label: "HIGH" | "MEDIUM" | "LOW";
  value: number | undefined;
  accent: string;
}) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/40 p-3">
      <p className="text-xs uppercase tracking-wider text-zinc-500">{label}</p>
      <p className={`mt-1 text-2xl font-bold tabular-nums ${accent}`}>
        {typeof value === "number" ? value.toLocaleString() : "—"}
      </p>
    </div>
  );
}
