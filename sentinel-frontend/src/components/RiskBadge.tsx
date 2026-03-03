interface RiskBadgeProps {
  severity: "HIGH" | "MEDIUM" | "LOW" | string;
}

const colorMap: Record<string, string> = {
  HIGH: "bg-red-500/15 text-red-500 border-red-500/30",
  MEDIUM: "bg-yellow-400/15 text-yellow-400 border-yellow-400/30",
  LOW: "bg-blue-400/15 text-blue-400 border-blue-400/30",
};

export default function RiskBadge({ severity }: RiskBadgeProps) {
  const colors = colorMap[severity] ?? "bg-zinc-700/30 text-zinc-400 border-zinc-600";

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${colors}`}
    >
      {severity}
    </span>
  );
}
