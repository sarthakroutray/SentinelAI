import type { Queues } from "@/lib/api";

interface QueueStatusProps {
  queues: Queues | null;
}

const items: { key: keyof Queues; label: string; description: string }[] = [
  { key: "main", label: "Main Queue", description: "Pending log evaluations" },
  { key: "processing", label: "Processing", description: "Currently being evaluated" },
  { key: "dlq", label: "Dead Letter Queue", description: "Failed after max retries" },
];

export default function QueueStatus({ queues }: QueueStatusProps) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      {items.map(({ key, label, description }) => {
        const value = queues ? queues[key] : null;
        const isDanger = key === "dlq" && value != null && value > 0;

        return (
          <div
            key={key}
            className={`rounded-lg border p-4 ${
              isDanger
                ? "border-red-500/40 bg-red-500/5"
                : "border-zinc-800 bg-zinc-900/90"
            }`}
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-zinc-300">{label}</p>
              <span
                className={`text-2xl font-bold tabular-nums ${
                  isDanger ? "text-red-400" : "text-zinc-100"
                }`}
              >
                {value != null ? value : "—"}
              </span>
            </div>
            <p className="mt-1 text-xs text-zinc-500">{description}</p>
          </div>
        );
      })}
    </div>
  );
}
