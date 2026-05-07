import { memo } from "react";

type KnowledgeGraphEmptyStateProps = {
  error: string;
};

function KnowledgeGraphEmptyStateComponent({ error }: KnowledgeGraphEmptyStateProps) {
  return (
    <div className="flex items-center justify-center h-full text-slate-400">
      <div className="text-center">
        <div className="text-5xl mb-3">🕸️</div>
        <p className="text-lg">知识图谱为空</p>
        <p className="text-sm mt-1">{error || "点击\"导入示例数据\"添加演示数据"}</p>
        <p className="text-xs mt-3 text-slate-300">
          确保 Neo4j 服务已启动 (bolt://localhost:7687)
        </p>
      </div>
    </div>
  );
}

export const KnowledgeGraphEmptyState = memo(KnowledgeGraphEmptyStateComponent);
