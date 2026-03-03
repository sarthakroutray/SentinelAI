"use client";

import { useEffect, useState } from "react";
import { fetchIpProfile, type Alert, type IpProfile } from "@/lib/api";
import RiskBadge from "./RiskBadge";

interface AlertModalProps {
  alert: Alert | null;
  isOpen: boolean;
  onClose: () => void;
}

export default function AlertModal({ alert, isOpen, onClose }: AlertModalProps) {
  const [visible, setVisible] = useState(false);
  const [ipProfile, setIpProfile] = useState<IpProfile | null>(null);
  const [isLoadingProfile, setIsLoadingProfile] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      const id = requestAnimationFrame(() => setVisible(true));
      return () => cancelAnimationFrame(id);
    }
    const id = requestAnimationFrame(() => setVisible(false));
    return () => cancelAnimationFrame(id);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!isOpen || !alert) {
      setIpProfile(null);
      setIsLoadingProfile(false);
      setProfileError(null);
      return;
    }

    const ip = alert.log?.ip_address;
    if (!ip) {
      setIpProfile(null);
      setIsLoadingProfile(false);
      setProfileError(null);
      return;
    }

    let cancelled = false;
    setIsLoadingProfile(true);
    setProfileError(null);

    void (async () => {
      try {
        const profile = await fetchIpProfile(ip);
        if (!cancelled) {
          setIpProfile(profile);
        }
      } catch {
        if (!cancelled) {
          setIpProfile(null);
          setProfileError("Failed to load IP profile");
        }
      } finally {
        if (!cancelled) {
          setIsLoadingProfile(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [alert, isOpen]);

  if (!isOpen || !alert) {
    return null;
  }

  const statisticalScore = extractScore(alert.score_breakdown, "statistical");
  const isolationScore = extractScore(alert.score_breakdown, "isolation");

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center p-4 transition-opacity duration-200 ${
        visible ? "opacity-100" : "opacity-0"
      }`}
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-black/70" />

      <div
        className={`relative z-10 w-full max-w-5xl rounded-xl border border-zinc-800 bg-zinc-950 shadow-2xl transition-all duration-200 ${
          visible ? "translate-y-0 scale-100" : "translate-y-2 scale-[0.98]"
        }`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-zinc-100">Alert Details</h3>
            <span className="rounded border border-zinc-700 bg-zinc-900 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-300">
              v1
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1 text-xs text-zinc-300 transition-colors hover:bg-zinc-800"
          >
            Close
          </button>
        </div>

        <div className="grid gap-0 lg:grid-cols-3">
          <div className="border-b border-zinc-800 px-5 py-4 lg:col-span-2 lg:border-b-0 lg:border-r">
            <div className="grid gap-4 sm:grid-cols-2">
              <InfoRow label="Timestamp" value={formatFullTimestamp(alert.created_at)} mono />
              <InfoRow label="IP Address" value={alert.log?.ip_address ?? "—"} mono />

              <div>
                <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">Severity</p>
                <RiskBadge severity={alert.severity} />
              </div>

              <div>
                <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">Risk Score</p>
                <div className="flex items-center gap-2">
                  <span className="w-10 text-right font-mono text-xs tabular-nums text-zinc-300">
                    {alert.risk_score.toFixed(2)}
                  </span>
                  <div className="h-2 w-36 overflow-hidden rounded-full bg-zinc-800">
                    <div
                      className={`h-full rounded-full ${riskBarColor(alert.risk_score)}`}
                      style={{ width: `${Math.min(alert.risk_score * 100, 100)}%` }}
                    />
                  </div>
                </div>
              </div>

              <InfoRow
                label="Anomaly Type"
                value={alert.anomaly_type ? alert.anomaly_type.replace(/\+/g, " · ") : "—"}
              />
              <InfoRow label="Rule Match Explanation" value={alert.reason || "—"} />
              <InfoRow label="Statistical Score" value={statisticalScore} mono />
              <InfoRow label="Isolation Score" value={isolationScore ?? "—"} mono />
            </div>

            <div className="mt-4 border-t border-zinc-800 pt-4">
              <p className="mb-2 text-xs uppercase tracking-wide text-zinc-500">Score Breakdown (JSON)</p>
              <pre className="max-h-56 overflow-auto rounded-md border border-zinc-800 bg-zinc-900 p-3 text-xs text-zinc-300">
                {JSON.stringify(alert.score_breakdown ?? {}, null, 2)}
              </pre>
            </div>
          </div>

          <div className="px-5 py-4">
            <p className="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">IP Profile</p>

            {isLoadingProfile && (
              <div className="rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-400">
                Loading profile…
              </div>
            )}

            {!isLoadingProfile && profileError && (
              <div className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
                {profileError}
              </div>
            )}

            {!isLoadingProfile && !profileError && !alert.log?.ip_address && (
              <div className="rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-500">
                No IP address available for this alert.
              </div>
            )}

            {!isLoadingProfile && !profileError && alert.log?.ip_address && !ipProfile && (
              <div className="rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-500">
                No profile found for this IP.
              </div>
            )}

            {!isLoadingProfile && ipProfile && (
              <div className="space-y-3 rounded-md border border-zinc-800 bg-zinc-900 p-3">
                <ProfileRow label="Total logs" value={ipProfile.total_logs.toLocaleString()} />
                <ProfileRow label="Error ratio" value={ipProfile.error_ratio.toFixed(2)} />
                <ProfileRow label="Avg risk" value={ipProfile.avg_risk_score.toFixed(2)} />
                <ProfileRow label="Recent alerts" value={ipProfile.recent_alert_count.toLocaleString()} />
                <ProfileRow label="Last seen" value={formatFullTimestamp(ipProfile.last_seen)} />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function InfoRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className={mono ? "font-mono text-xs text-zinc-300" : "text-sm text-zinc-300"}>{value}</p>
    </div>
  );
}

function ProfileRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 text-sm text-zinc-300">{value}</p>
    </div>
  );
}

function formatFullTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZoneName: "short",
  });
}

function riskBarColor(score: number): string {
  if (score >= 0.7) return "bg-red-500";
  if (score >= 0.4) return "bg-yellow-400";
  if (score >= 0.2) return "bg-blue-400";
  return "bg-zinc-600";
}

function extractScore(breakdown: Record<string, number>, key: "statistical" | "isolation") {
  const value = breakdown?.[key];
  if (typeof value !== "number") return key === "isolation" ? null : "0.00";
  return value.toFixed(2);
}
