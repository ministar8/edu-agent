import { memo } from "react";

import type { Governance } from "@/types/chat";

const CONFIDENCE_STYLES: Record<string, { className: string; label: string }> = {
  high: { className: "bg-green-100 text-green-700", label: "有依据" },
  medium: { className: "bg-yellow-100 text-yellow-700", label: "部分依据" },
  low: { className: "bg-red-100 text-red-700", label: "依据不足" },
};

const DEFAULT_STYLE = { className: "bg-slate-100 text-slate-600", label: "待评估" };

function GovernanceBadgeComponent({ governance }: { governance: Governance }) {
  const { className, label } = CONFIDENCE_STYLES[governance.confidence] ?? DEFAULT_STYLE;
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${className}`}>
      {label}
    </span>
  );
}

export const GovernanceBadge = memo(GovernanceBadgeComponent);
