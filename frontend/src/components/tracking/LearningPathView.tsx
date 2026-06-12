"use client";

import { useEffect, useRef, useState } from "react";
import { http } from "@/lib/http";
import { getErrorMessage } from "@/lib/errors";
import { useTrackingRefresh } from "@/contexts/TrackingRefreshContext";
import { CATEGORY_LABELS } from "@/lib/collections";

// ── Types ────────────────────────────────────────────────────

interface ChainNode {
  name: string;
  description: string;
  mastery?: number | null;
  is_target?: boolean;
}

interface LearningPath {
  target: string;
  category: string;
  effective_score: number;
  chain: ChainNode[];
}

// ── Mastery color helpers ────────────────────────────────────

function masteryColor(mastery: number | null | undefined): string {
  if (mastery == null) return "bg-slate-200 text-slate-500";
  const pct = Math.round(Math.max(0, Math.min(1, mastery)) * 100);
  if (pct >= 60) return "bg-emerald-100 text-emerald-700 border-emerald-200";
  if (pct >= 30) return "bg-amber-100 text-amber-700 border-amber-200";
  return "bg-red-100 text-red-600 border-red-200";
}

function masteryLabel(mastery: number | null | undefined): string {
  if (mastery == null) return "未学习";
  const pct = Math.round(Math.max(0, Math.min(1, mastery)) * 100);
  return `${pct}%`;
}

// ── Component ────────────────────────────────────────────────

type LearningPathViewProps = {
  onGenerateSimilarPractice?: (topic: string) => void;
};

export default function LearningPathView({ onGenerateSimilarPractice }: LearningPathViewProps = {}) {
  const [paths, setPaths] = useState<LearningPath[]>([]);
  const { refreshVersion } = useTrackingRefresh();
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const res = await http.get("/api/tracking/learning-path", { params: { limit: 5 } });
        if (!mountedRef.current) return;
        setPaths(res.data?.data || []);
      } catch (e: unknown) {
        if (!mountedRef.current) return;
        setError(getErrorMessage(e, "学习路径加载失败"));
      } finally {
        if (mountedRef.current) setLoading(false);
      }
    })();
  }, [refreshVersion]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-slate-400">
        加载学习路径...
      </div>
    );
  }

  if (error) {
    return <div className="text-sm text-red-500 py-4">{error}</div>;
  }

  if (paths.length === 0) {
    return <div className="text-sm text-slate-400 py-4">暂无薄弱知识点，无需学习路径！</div>;
  }

  return (
    <div className="space-y-4">
      {paths.map((path, idx) => {
        const isExpanded = expandedIdx === idx;
        const catLabel = CATEGORY_LABELS[path.category] || path.category;
        const targetPct = Math.round(Math.max(0, Math.min(1, path.effective_score)) * 100);

        return (
          <div key={idx} className="rounded-xl border border-slate-200 overflow-hidden">
            {/* Header */}
            <div
              className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-slate-50 transition-colors"
              onClick={() => setExpandedIdx(isExpanded ? null : idx)}
            >
              {/* Target badge */}
              <div className={`shrink-0 w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold border ${
                targetPct >= 30 ? "bg-red-100 text-red-600 border-red-200" : "bg-amber-100 text-amber-600 border-amber-200"
              }`}>
                {targetPct}%
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-slate-800 truncate">{path.target}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 shrink-0">{catLabel}</span>
                </div>
                <div className="text-xs text-slate-400 mt-0.5">
                  需学习 {path.chain.length - 1} 个前置知识
                </div>
              </div>
              {/* Expand arrow */}
              <svg
                className={`w-4 h-4 text-slate-400 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </div>

            {/* Expanded chain */}
            {isExpanded && (
              <div className="px-4 pb-4 pt-1 border-t border-slate-100">
                <div className="flex flex-col">
                  {path.chain.map((node, stepIdx) => {
                    const isLast = stepIdx === path.chain.length - 1;
                    const isTarget = node.is_target;
                    const mColor = masteryColor(node.mastery);

                    return (
                      <div key={stepIdx} className="flex items-start gap-3">
                        {/* Vertical line + circle */}
                        <div className="flex flex-col items-center shrink-0">
                          <div
                            className={`w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold border shrink-0 ${
                              isTarget
                                ? "bg-red-500 text-white border-red-500"
                                : mColor
                            }`}
                          >
                            {isTarget ? "!" : stepIdx + 1}
                          </div>
                          {!isLast && (
                            <div className="w-0.5 h-6 bg-slate-200" />
                          )}
                        </div>

                        {/* Node content */}
                        <div className={`flex-1 min-w-0 pb-3 ${isLast ? "pb-0" : ""}`}>
                          <div className="flex items-center gap-2">
                            <span className={`text-sm font-medium truncate ${
                              isTarget ? "text-red-600" : "text-slate-700"
                            }`}>
                              {node.name}
                            </span>
                            {node.mastery != null && (
                              <span className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 ${mColor}`}>
                                {masteryLabel(node.mastery)}
                              </span>
                            )}
                            {node.mastery == null && !isTarget && (
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-400 shrink-0">
                                未学习
                              </span>
                            )}
                            {isTarget && (
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-50 text-red-500 shrink-0">
                                目标
                              </span>
                            )}
                            {isTarget && onGenerateSimilarPractice && (
                              <button
                                type="button"
                                onClick={(e) => { e.stopPropagation(); onGenerateSimilarPractice(node.name); }}
                                className="rounded-full bg-orange-100 px-2 py-0.5 text-[10px] font-medium text-orange-700 hover:bg-orange-200 transition-colors shrink-0"
                              >
                                去练习
                              </button>
                            )}
                          </div>
                          {node.description && (
                            <div className="text-xs text-slate-400 mt-0.5 line-clamp-2">{node.description}</div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
