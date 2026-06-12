"use client";

import { memo } from "react";

import type { KGTrace } from "@/types/rag";

type KGTracePanelProps = {
  kg: KGTrace | null;
};

function KGTracePanelComponent({ kg }: KGTracePanelProps) {
  if (!kg || kg.skipped) return null;

  return (
    <div className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-base font-semibold text-slate-800">知识图谱证据</h3>
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-medium ${
            kg.used ? "bg-emerald-50 text-emerald-700" : "bg-slate-50 text-slate-400"
          }`}
        >
          {kg.used ? "已命中" : "未命中"}
        </span>
      </div>

      {kg.used ? (
        <div className="space-y-3">
          {/* Stats row */}
          <div className="grid grid-cols-3 gap-2">
            <div className="rounded-xl bg-indigo-50 px-3 py-2 text-center">
              <div className="text-lg font-bold text-indigo-700">{kg.nodes_count}</div>
              <div className="text-[10px] text-indigo-500">节点</div>
            </div>
            <div className="rounded-xl bg-violet-50 px-3 py-2 text-center">
              <div className="text-lg font-bold text-violet-700">{kg.edges_count}</div>
              <div className="text-[10px] text-violet-500">边</div>
            </div>
            <div className="rounded-xl bg-emerald-50 px-3 py-2 text-center">
              <div className="text-lg font-bold text-emerald-700">{kg.paths_count}</div>
              <div className="text-[10px] text-emerald-500">路径</div>
            </div>
          </div>

          {/* Resolved topics */}
          {kg.resolved_topics.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-medium text-slate-500">解析主题</p>
              <div className="flex flex-wrap gap-1.5">
                {kg.resolved_topics.map((topic, i) => (
                  <span
                    key={i}
                    className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700"
                  >
                    {topic}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Sample nodes */}
          {kg.sample_nodes.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-medium text-slate-500">相关节点</p>
              <div className="flex flex-wrap gap-1.5">
                {kg.sample_nodes.slice(0, 8).map((node, i) => (
                  <span
                    key={i}
                    className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-700"
                  >
                    {node}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Sample paths */}
          {kg.sample_paths.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-medium text-slate-500">知识路径</p>
              <div className="space-y-1">
                {kg.sample_paths.slice(0, 3).map((path, i) => (
                  <div
                    key={i}
                    className="rounded-lg border border-emerald-100 bg-emerald-50/50 px-3 py-1.5 text-xs text-emerald-700"
                  >
                    {path}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Category */}
          {kg.category && (
            <div className="text-xs text-slate-400">
              类别: <span className="font-medium text-slate-600">{kg.category}</span>
            </div>
          )}
        </div>
      ) : (
        <div className="py-4 text-center text-sm text-slate-400">
          {kg.error ? `KG查询失败: ${kg.error}` : "未找到匹配的知识图谱数据"}
        </div>
      )}
    </div>
  );
}

export const KGTracePanel = memo(KGTracePanelComponent);
