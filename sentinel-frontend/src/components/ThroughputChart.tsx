"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface ThroughputChartProps {
  timestamps: string[];
  logs: number[];
  alerts: number[];
}

export default function ThroughputChart({ timestamps, logs, alerts }: ThroughputChartProps) {
  const data = useMemo(
    () =>
      timestamps.map((timestamp, index) => ({
        time: formatMinute(timestamp),
        logs: logs[index] ?? 0,
        alerts: alerts[index] ?? 0,
      })),
    [timestamps, logs, alerts],
  );

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/90 p-4">
      <div className="mb-3 flex items-center gap-2">
        <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
          Throughput (last minutes)
        </p>
        <span className="rounded border border-zinc-700 bg-zinc-950 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-300">
          v1
        </span>
      </div>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
            <XAxis dataKey="time" tick={{ fill: "#71717a", fontSize: 11 }} />
            <YAxis allowDecimals={false} tick={{ fill: "#71717a", fontSize: 11 }} />
            <Tooltip
              contentStyle={{
                backgroundColor: "#09090b",
                border: "1px solid #27272a",
                borderRadius: "0.5rem",
                color: "#e4e4e7",
              }}
              labelStyle={{ color: "#a1a1aa" }}
            />
            <Line type="monotone" dataKey="logs" stroke="#34d399" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="alerts" stroke="#f43f5e" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function formatMinute(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
