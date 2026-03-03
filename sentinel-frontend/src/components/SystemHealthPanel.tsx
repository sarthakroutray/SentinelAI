import type { HealthStatus } from "@/lib/api";

interface SystemHealthPanelProps {
  health: HealthStatus | null;
}

export default function SystemHealthPanel({ health }: SystemHealthPanelProps) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/90 p-5">
      <div className="mb-3 flex items-center gap-2">
        <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">System Health</p>
        <span className="rounded border border-zinc-700 bg-zinc-950 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-300">
          v1
        </span>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <HealthItem
          label="DB Latency"
          value={health ? `${health.db_latency_ms.toFixed(2)} ms` : "—"}
          tone={health ? latencyTone(health.db_latency_ms) : "warning"}
        />
        <HealthItem
          label="Worker"
          value={health ? (health.worker_alive ? "Alive" : "Offline") : "—"}
          tone={health ? (health.worker_alive ? "healthy" : "failure") : "warning"}
        />
        <HealthItem
          label="Queue Depth"
          value={health ? health.queue_depth.toLocaleString() : "—"}
          tone={health ? queueTone(health.queue_depth) : "warning"}
        />
        <HealthItem
          label="Last Retrain"
          value={health?.last_model_retrain ? formatTime(health.last_model_retrain) : "Never"}
          tone={health?.last_model_retrain ? "healthy" : "warning"}
        />
      </div>
    </div>
  );
}

function HealthItem({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "healthy" | "warning" | "failure";
}) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/40 p-3">
      <div className="flex items-center gap-2">
        <span className={`inline-block h-2.5 w-2.5 rounded-full ${toneColor(tone)}`} />
        <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      </div>
      <p className="mt-2 text-sm text-zinc-200">{value}</p>
    </div>
  );
}

function latencyTone(ms: number): "healthy" | "warning" | "failure" {
  if (ms < 100) return "healthy";
  if (ms < 300) return "warning";
  return "failure";
}

function queueTone(depth: number): "healthy" | "warning" | "failure" {
  if (depth < 20) return "healthy";
  if (depth < 100) return "warning";
  return "failure";
}

function toneColor(tone: "healthy" | "warning" | "failure"): string {
  if (tone === "healthy") return "bg-emerald-500";
  if (tone === "warning") return "bg-yellow-400";
  return "bg-red-500";
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}
