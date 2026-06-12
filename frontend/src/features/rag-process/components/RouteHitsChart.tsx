"use client";

import { memo, useMemo } from "react";

import type { RAGTrace } from "@/shared/types/rag";

type RouteHitsChartProps = {
  trace: RAGTrace | null;
};

const ROUTE_COLORS: Record<string, string> = {
  semantic: "bg-indigo-400",
  keyword_bm25: "bg-emerald-400",
  expanded: "bg-violet-400",
  concept_meta: "bg-amber-400",
  comparison_meta: "bg-rose-400",
  exercise_meta: "bg-cyan-400",
  answer_meta: "bg-pink-400",
  code_meta: "bg-orange-400",
  heading_meta: "bg-teal-400",
  chapter_meta: "bg-lime-400",
};

function RouteHitsChartComponent({ trace }: RouteHitsChartProps) {
  const routeData = useMemo(() => {
    if (!trace) return [];
    const hits = trace.route_summary.hits_by_route;
    return Object.entries(hits)
      .sort(([, a], [, b]) => b - a)
      .map(([route, count]) => ({
        route,
        count,
        color: ROUTE_COLORS[route] || "bg-slate-400",
      }));
  }, [trace]);

  const collectionData = useMemo(() => {
    if (!trace) return [];
    const hits = trace.route_summary.hits_by_collection;
    return Object.entries(hits)
      .sort(([, a], [, b]) => b - a)
      .map(([collection, count]) => ({ collection, count }));
  }, [trace]);

  if (!trace || routeData.length === 0) return null;

  const maxHits = Math.max(...routeData.map((d) => d.count), 1);

  return (
    <div className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="mb-4 text-base font-semibold text-slate-800">路由命中统计</h3>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* By route */}
        <div>
          <p className="mb-2 text-xs font-medium text-slate-500">按路由类型</p>
          <div className="space-y-2">
            {routeData.map(({ route, count, color }) => (
              <div key={route} className="flex items-center gap-2">
                <span className="w-24 truncate text-xs text-slate-600" title={route}>
                  {route}
                </span>
                <div className="flex-1">
                  <div className="h-5 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${color}`}
                      style={{ width: `${(count / maxHits) * 100}%` }}
                    />
                  </div>
                </div>
                <span className="w-8 text-right text-xs font-medium text-slate-700">{count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* By collection */}
        <div>
          <p className="mb-2 text-xs font-medium text-slate-500">按集合</p>
          <div className="space-y-2">
            {collectionData.map(({ collection, count }) => (
              <div key={collection} className="flex items-center gap-2">
                <span className="w-24 truncate text-xs text-slate-600" title={collection}>
                  {collection}
                </span>
                <div className="flex-1">
                  <div className="h-5 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-blue-400 transition-all duration-500"
                      style={{
                        width: `${(count / Math.max(...collectionData.map((d) => d.count), 1)) * 100}%`,
                      }}
                    />
                  </div>
                </div>
                <span className="w-8 text-right text-xs font-medium text-slate-700">{count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Total stats */}
      <div className="mt-3 flex items-center gap-4 border-t border-slate-100 pt-3 text-xs text-slate-500">
        <span>总路由数: <strong className="text-slate-700">{trace.route_summary.total_routes}</strong></span>
        <span>总命中: <strong className="text-slate-700">{trace.route_summary.total_hits}</strong></span>
      </div>
    </div>
  );
}

export const RouteHitsChart = memo(RouteHitsChartComponent);
