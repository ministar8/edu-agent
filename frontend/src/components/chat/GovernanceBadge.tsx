import { memo } from "react";

import type { Governance } from "@/types/chat";

function GovernanceBadgeComponent({ governance }: { governance: Governance }) {
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
      governance.confidence === "high"
        ? "bg-green-100 text-green-700"
        : governance.confidence === "medium"
        ? "bg-yellow-100 text-yellow-700"
        : "bg-red-100 text-red-700"
    }`}>
      {governance.confidence === "high" ? "有依据" : governance.confidence === "medium" ? "部分依据" : "依据不足"}
    </span>
  );
}

export const GovernanceBadge = memo(GovernanceBadgeComponent);
