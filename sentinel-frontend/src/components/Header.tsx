"use client";

import { useEffect, useState } from "react";

type WSStatus = "connected" | "connecting" | "reconnecting" | "disconnected";

export default function Header() {
  const [health, setHealth] = useState<"ok" | "down" | "checking">("checking");
  const [wsStatus, setWsStatus] = useState<WSStatus>("disconnected");

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const base = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
        const res = await fetch(`${base}/health`, { cache: "no-store" });
        if (!cancelled) setHealth(res.ok ? "ok" : "down");
      } catch {
        if (!cancelled) setHealth("down");
      }
    };
    check();
    const id = setInterval(check, 15_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    const handler = (ev: Event) => {
      try {
        const detail = (ev as CustomEvent).detail as { status?: string } | undefined;
        const s = detail?.status;
        if (s === "connected" || s === "connecting" || s === "reconnecting" || s === "disconnected") {
          setWsStatus(s as WSStatus);
        }
      } catch {
        // ignore
      }
    };

    window.addEventListener("dashboard-ws-status", handler as EventListener);
    return () => window.removeEventListener("dashboard-ws-status", handler as EventListener);
  }, []);

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-zinc-800 bg-zinc-950/90 px-6 backdrop-blur">
      <div className="flex items-center gap-2">
        <h1 className="text-sm font-semibold text-zinc-200">Security Dashboard</h1>
        <span className="rounded border border-zinc-700 bg-zinc-900 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-300">
          v1
        </span>
      </div>

      <div className="flex items-center gap-3">
        {/* API health dot */}
        <span className="flex items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900/70 px-2 py-1 text-xs text-zinc-400">
          <span
            className={`inline-block h-2 w-2 rounded-full ${
              health === "ok"
                ? "bg-emerald-500"
                : health === "down"
                ? "bg-red-500"
                : "bg-zinc-600 animate-pulse"
            }`}
          />
          API {health === "ok" ? "Connected" : health === "down" ? "Offline" : "Checking…"}
        </span>
        {/* WebSocket status dot */}
        <span className="flex items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900/70 px-2 py-1 text-xs text-zinc-400">
          <span
            className={`inline-block h-2 w-2 rounded-full ${
              wsStatus === "connected"
                ? "bg-emerald-400"
                : wsStatus === "disconnected"
                ? "bg-red-500"
                : "bg-amber-500 animate-pulse"
            }`}
          />
          Real-time {wsStatus === "connected" ? "Online" : wsStatus === "disconnected" ? "Offline" : "Connecting…"}
        </span>
      </div>
    </header>
  );
}
