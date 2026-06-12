import { memo } from "react";

type KnowledgeGraphEmptyStateProps = {
  error: string;
};

function KnowledgeGraphEmptyStateComponent({ error }: KnowledgeGraphEmptyStateProps) {
  return (
    <div className="flex h-full items-center justify-center bg-slate-50 text-slate-400">
      <div className="max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-900 text-xl font-bold text-white">KG</div>
        <p className="text-lg font-bold text-slate-800">暂无可展示的知识图谱</p>
        <p className="mt-2 text-sm leading-6 text-slate-500">{error || "点击“导入演示图谱”添加适合答辩展示的 408 四科知识结构数据。"}</p>
        <p className="mt-4 text-xs text-slate-300">
          确保 Neo4j 服务已启动 (bolt://localhost:7687)
        </p>
      </div>
    </div>
  );
}

export const KnowledgeGraphEmptyState = memo(KnowledgeGraphEmptyStateComponent);
