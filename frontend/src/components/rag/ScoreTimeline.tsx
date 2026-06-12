"use client";

import { memo } from "react";

import type { RAGTrace, ScoreStats } from "@/types/rag";

type ScoreTimelineProps = {
  trace: RAGTrace | null;
};

const STAGES = [
  { key: "after_threshold", label: "阈值过滤后" },
  { key: "after_rerank", label: "重排后" },
  { key: "after_hyde", label: "HyDE后" },
  { key: "final", label: "最终" },
] as const;

function ScoreBar({ label, stats, maxScore }: { label: string; stats: ScoreStats; maxScore: number }) {
  if (stats.top === 0 && stats.avg === 0) return null;

  return (
    <div className="flex items-center gap-3">
      <span className="w-20 text-xs text-slate-500">{label}</span>
      <div className="flex-1">
        {/* Top score bar */}
        <div className="mb-1 flex items-center gap-2">
          <span className="w-8 text-[10px] text-slate-400">Top</span>
          <div className="flex-1">
            <div className="h-3 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-emerald-400 transition-all duration-500"
                style={{ width: `${Math.min((stats.top / maxScore) * 100, 100)}%` }}
              />
            </div>
          </div>
          <span className="w-14 text-right text-xs font-mono font-medium text-emerald-700">
            {stats.top.toFixed(3)}
          </span>
        </div>
        {/* Avg score bar */}
        <div className="flex items-center gap-2">
          <span className="w-8 text-[10px] text-slate-400">Avg</span>
          <div className="flex-1">
            <div className="h-3 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-indigo-400 transition-all duration-500"
                style={{ width: `${Math.min((stats.avg / maxScore) * 100, 100)}%` }}
              />
            </div>
          </div>
          <span className="w-14 text-right text-xs font-mono font-medium text-indigo-700">
            {stats.avg.toFixed(3)}
          </span>
        </div>
      </div>
    </div>
  );
}

function ScoreTimelineComponent({ trace }: ScoreTimelineProps) {
  if (!trace) return null;

  const scoreStats = trace.score_stats;
  const maxScore = Math.max(
    ...Object.values(scoreStats).map((s) => s.top || 0),
    0.01,
  );

  // Rerank info
  const rerank = trace.rerank;
  const hyde = trace.hyde;

  return (
    <div className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="mb-4 text-base font-semibold text-slate-800">分数变化追踪</h3>

      <div className="space-y-4">
        {STAGES.map((stage) => {
          const stats = scoreStats[stage.key as keyof typeof scoreStats];
          return <ScoreBar key={stage.key} label={stage.label} stats={stats} maxScore={maxScore} />;
        })}
      </div>

      {/* Rerank & HyDE status */}
      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-slate-100 pt-3">
        <div
          className={`rounded-xl px-3 py-2 text-xs ${
            rerank.enabled ? "bg-emerald-50 text-emerald-700" : "bg-slate-50 text-slate-400"
          }`}
        >
          <div className="font-medium">Rerank</div>
          <div>
            {rerank.enabled
              ? `Top: ${rerank.top_score.toFixed(3)} | 保留: ${rerank.kept}`
              : "未启用"}
          </div>
        </div>
        <div
          className={`rounded-xl px-3 py-2 text-xs ${
            hyde.triggered ? "bg-amber-50 text-amber-700" : hyde.skipped ? "bg-slate-50 text-slate-400" : "bg-slate-50 text-slate-500"
          }`}
        >
          <div className="font-medium">HyDE</div>
          <div>
            {hyde.skipped
              ? "已跳过"
              : hyde.triggered
                ? `触发 | 新增: ${hyde.added_count}`
                : "未触发"}
          </div>
        </div>
      </div>
    </div>
  );
}

export const ScoreTimeline = memo(ScoreTimelineComponent);
