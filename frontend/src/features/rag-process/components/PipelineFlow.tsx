"use client";

import { memo } from "react";

import type { RAGTrace } from "@/shared/types/rag";

type PipelineFlowProps = {
  trace: RAGTrace | null;
};

const STAGES = [
  { key: "raw", label: "粗召回", icon: "🔍" },
  { key: "after_dedup", label: "去重", icon: "🔄" },
  { key: "after_threshold", label: "阈值过滤", icon: "📐" },
  { key: "after_rerank", label: "重排", icon: "📊" },
  { key: "after_hyde", label: "HyDE", icon: "💡" },
  { key: "after_window", label: "窗口展开", icon: "🪟" },
  { key: "final", label: "最终结果", icon: "✅" },
] as const;

function PipelineFlowComponent({ trace }: PipelineFlowProps) {
  if (!trace) return null;

  const counts = trace.counts;
  const depth = trace.policy.retrieval_depth;
  const duration = trace.duration_ms;

  return (
    <div className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-base font-semibold text-slate-800">检索管线流程</h3>
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span className="rounded-full bg-indigo-50 px-2.5 py-1 font-medium text-indigo-600">
            {depth} 深度
          </span>
          <span>{duration.toFixed(0)}ms</span>
        </div>
      </div>

      {/* Horizontal pipeline flow */}
      <div className="flex items-center gap-0 overflow-x-auto pb-2">
        {STAGES.map((stage, i) => {
          const count = counts[stage.key as keyof typeof counts] ?? 0;
          const prevCount = i > 0 ? counts[STAGES[i - 1].key as keyof typeof counts] ?? 0 : 0;
          const isDrop = count < prevCount;
          const isGain = count > prevCount;
          const barMax = Math.max(counts.raw, 1);
          const barPct = Math.min((count / barMax) * 100, 100);

          return (
            <div key={stage.key} className="flex items-center">
              {/* Arrow connector */}
              {i > 0 && (
                <div className="mx-1 flex flex-col items-center">
                  <div className="h-px w-4 bg-slate-300" />
                  <span className="text-[10px] text-slate-400">
                    {isDrop ? "↓" : isGain ? "↑" : "→"}
                  </span>
                </div>
              )}

              {/* Stage node */}
              <div className="flex min-w-[72px] flex-col items-center gap-1.5">
                <span className="text-lg">{stage.icon}</span>
                <span className="text-[11px] font-medium text-slate-600">{stage.label}</span>
                <span
                  className={`text-sm font-bold ${
                    count === 0
                      ? "text-slate-300"
                      : isDrop && i > 0
                        ? "text-amber-600"
                        : isGain && i > 0
                          ? "text-emerald-600"
                          : "text-slate-800"
                  }`}
                >
                  {count}
                </span>
                {/* Mini bar */}
                <div className="h-1.5 w-12 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      count === 0
                        ? "bg-slate-200"
                        : isDrop && i > 0
                          ? "bg-amber-400"
                          : isGain && i > 0
                            ? "bg-emerald-400"
                            : "bg-indigo-400"
                    }`}
                    style={{ width: `${barPct}%` }}
                  />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Decomposition info */}
      {trace.decomposition.decomposed && (
        <div className="mt-3 rounded-xl border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-700">
          查询分解为 {trace.decomposition.sub_queries.length} 个子查询：
          {trace.decomposition.sub_queries.map((sq, i) => (
            <span key={i} className="ml-1 inline-block rounded bg-blue-100 px-1.5 py-0.5">
              {sq.length > 20 ? sq.slice(0, 20) + "…" : sq}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export const PipelineFlow = memo(PipelineFlowComponent);
