"use client";

import { useEffect, useRef } from "react";
import type { Alert, Metrics } from "@/lib/api";

type DashboardMessage =
  | { type: "alert"; payload: Alert }
  | { type: "metrics"; payload: Metrics };

interface UseDashboardWebSocketOptions {
  onAlert: (alert: Alert) => void;
  onMetrics: (metrics: Metrics) => void;
}

const BASE_RETRY_MS = 1_000;
const MAX_RETRY_MS = 30_000;

export function useDashboardWebSocket({ onAlert, onMetrics }: UseDashboardWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const shouldRunRef = useRef(true);
  const retryRef = useRef(0);
  const onAlertRef = useRef(onAlert);
  const onMetricsRef = useRef(onMetrics);
  const statusRef = useRef<string>("disconnected");

  const emitStatus = (status: string) => {
    try {
      if (statusRef.current === status) return;
      statusRef.current = status;
      window.dispatchEvent(new CustomEvent("dashboard-ws-status", { detail: { status } }));
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    onAlertRef.current = onAlert;
    onMetricsRef.current = onMetrics;
  }, [onAlert, onMetrics]);

  useEffect(() => {
    shouldRunRef.current = true;

    const connect = () => {
      emitStatus("connecting");
      if (!shouldRunRef.current) return;

      const httpBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
      const wsBase = httpBase.startsWith("https://")
        ? httpBase.replace("https://", "wss://")
        : httpBase.replace("http://", "ws://");

      const socket = new WebSocket(`${wsBase}/ws/dashboard`);
      wsRef.current = socket;

      socket.onopen = () => {
        retryRef.current = 0;
        emitStatus("connected");
      };

      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as DashboardMessage;
          if (message.type === "alert") {
            onAlertRef.current(message.payload);
            return;
          }
          if (message.type === "metrics") {
            onMetricsRef.current(message.payload);
          }
        } catch {
          // Ignore malformed messages.
        }
      };

      socket.onclose = () => {
        if (!shouldRunRef.current) {
          emitStatus("disconnected");
          return;
        }

        const attempt = retryRef.current;
        const backoff = Math.min(BASE_RETRY_MS * 2 ** attempt, MAX_RETRY_MS);
        retryRef.current = attempt + 1;
        emitStatus("reconnecting");
        window.setTimeout(connect, backoff);
      };

      socket.onerror = () => {
        socket.close();
      };
    };

    connect();

    return () => {
      shouldRunRef.current = false;
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
        emitStatus("disconnected");
      }
    };
  }, []);
}
