"use client";

import { useState } from "react";

import { useRagProcess } from "@/features/rag-process/hooks/useRagProcess";
import { KGTracePanel } from "./KGTracePanel";
import { PipelineFlow } from "./PipelineFlow";
import { RouteHitsChart } from "./RouteHitsChart";
import { RagSearchCard } from "./RagSearchCard";
import { RagStepList } from "./RagStepList";
import { ScoreTimeline } from "./ScoreTimeline";

type ViewMode = "pipeline" | "steps" | "detail";

export default function RAGProcessPanel() {
  const {
    query,
    collection,
    steps,
    trace,
    resultText,
    loading,
    activeStep,
    setQuery,
    setCollection,
    searchRAG,
  } = useRagProcess();

  const [viewMode, setViewMode] = useState<ViewMode>("pipeline");

  const hasTrace = trace !== null;

  return (
    <div className="mx-auto flex h-full max-w-6xl flex-col gap-4 overflow-y-auto p-6 text-slate-800">
      {/* Search input */}
      <RagSearchCard
        query={query}
        collection={collection}
        loading={loading}
        onQueryChange={setQuery}
        onCollectionChange={setCollection}
        onSearch={() => void searchRAG()}
      />

      {/* View mode tabs (only when trace available) */}
      {hasTrace && (
        <div className="flex gap-1 rounded-2xl bg-slate-100 p-1">
          {([
            { key: "pipeline", label: "管线流程" },
            { key: "steps", label: "逐步展示" },
            { key: "detail", label: "详细分析" },
          ] as const).map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setViewMode(key)}
              className={`flex-1 rounded-xl px-3 py-2 text-xs font-medium transition ${
                viewMode === key
                  ? "bg-white text-slate-800 shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {/* Pipeline view */}
      {viewMode === "pipeline" && (
        <>
          <PipelineFlow trace={trace} />
          <div className="grid gap-4 lg:grid-cols-2">
            <RouteHitsChart trace={trace} />
            <ScoreTimeline trace={trace} />
          </div>
          <KGTracePanel kg={trace?.kg ?? null} />
        </>
      )}

      {/* Steps view (original) */}
      {viewMode === "steps" && (
        <RagStepList steps={steps} loading={loading} activeStep={activeStep} />
      )}

      {/* Detail view */}
      {viewMode === "detail" && trace && (
        <div className="space-y-4">
          {/* Policy summary */}
          <div className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="mb-3 text-base font-semibold text-slate-800">检索策略</h3>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { label: "检索深度", value: trace.policy.retrieval_depth },
                { label: "粗召回K", value: String(trace.policy.coarse_k) },
                { label: "有效K", value: String(trace.policy.effective_k) },
                { label: "阈值", value: trace.policy.threshold.toFixed(4) },
                { label: "Rerank", value: trace.policy.use_rerank ? "开启" : "关闭" },
                { label: "BM25", value: trace.policy.skip_bm25 ? "跳过" : "启用" },
                { label: "查询分解", value: trace.policy.skip_decompose ? "跳过" : "启用" },
                { label: "HyDE", value: trace.policy.skip_hyde ? "跳过" : "启用" },
              ].map(({ label, value }) => (
                <div key={label} className="rounded-xl bg-slate-50 px-3 py-2">
                  <div className="text-[10px] text-slate-400">{label}</div>
                  <div className="text-sm font-medium text-slate-700">{value}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Route details table */}
          {trace.routes.length > 0 && (
            <div className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="mb-3 text-base font-semibold text-slate-800">路由详情</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-slate-100 text-left text-slate-500">
                      <th className="pb-2 pr-3">集合</th>
                      <th className="pb-2 pr-3">路由</th>
                      <th className="pb-2 pr-3">查询</th>
                      <th className="pb-2 pr-3">命中</th>
                      <th className="pb-2 pr-3">Top分数</th>
                      <th className="pb-2">Top来源</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trace.routes.slice(0, 12).map((route, i) => (
                      <tr key={i} className="border-b border-slate-50">
                        <td className="py-1.5 pr-3 text-slate-600">{route.collection}</td>
                        <td className="py-1.5 pr-3">
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-600">
                            {route.route}
                          </span>
                        </td>
                        <td className="max-w-[120px] truncate py-1.5 pr-3 text-slate-500" title={route.route_query}>
                          {route.route_query}
                        </td>
                        <td className="py-1.5 pr-3 font-medium text-slate-700">{route.hits}</td>
                        <td className="py-1.5 pr-3 font-mono text-slate-600">
                          {route.top_score > 0 ? route.top_score.toFixed(4) : "-"}
                        </td>
                        <td className="max-w-[100px] truncate py-1.5 text-slate-500" title={route.top_source}>
                          {route.top_source || "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Result text preview */}
          {resultText && (
            <div className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="mb-3 text-base font-semibold text-slate-800">最终上下文预览</h3>
              <div className="max-h-60 overflow-y-auto rounded-xl bg-slate-50 p-4 text-xs leading-5 text-slate-600">
                {resultText}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {!hasTrace && !loading && steps.length === 0 && (
        <div className="flex flex-1 items-center justify-center">
          <div className="py-16 text-center text-slate-400">
            <div className="mb-3 text-5xl">🔍</div>
            <p>输入查询开始 RAG 检索过程可视化</p>
          </div>
        </div>
      )}

      {/* Loading state */}
      {loading && !hasTrace && (
        <div className="flex flex-1 items-center justify-center">
          <div className="py-10 text-center">
            <div className="inline-flex gap-2 text-3xl">
              <span className="animate-bounce" style={{ animationDelay: "0s" }}>📝</span>
              <span className="animate-bounce" style={{ animationDelay: "0.15s" }}>🔄</span>
              <span className="animate-bounce" style={{ animationDelay: "0.3s" }}>🔍</span>
              <span className="animate-bounce" style={{ animationDelay: "0.45s" }}>📊</span>
            </div>
            <p className="mt-3 text-slate-500">正在执行 RAG 检索管线...</p>
          </div>
        </div>
      )}
    </div>
  );
}
