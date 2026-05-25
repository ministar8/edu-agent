import { memo } from "react";

type KnowledgeGraphToolbarProps = {
  showImport: boolean;
  onRefresh: () => void;
  onToggleImport: () => void;
};

function KnowledgeGraphToolbarComponent({ showImport, onRefresh, onToggleImport }: KnowledgeGraphToolbarProps) {
  return (
    <div className="p-4 bg-white border-b flex items-center justify-between">
      <div>
        <h2 className="text-lg font-bold text-slate-800">知识图谱可视化</h2>
        <p className="text-sm text-slate-500">
          Neo4j 知识图谱 — 知识点依赖关系与学习路径
        </p>
      </div>
      <div className="flex gap-2">
        <button
          onClick={onRefresh}
          className="px-3 py-1.5 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200 text-sm"
        >
          刷新
        </button>
        <button
          onClick={onToggleImport}
          className="px-3 py-1.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 text-sm"
        >
          {showImport ? "收起导入" : "导入示例数据"}
        </button>
      </div>
    </div>
  );
}

export const KnowledgeGraphToolbar = memo(KnowledgeGraphToolbarComponent);
