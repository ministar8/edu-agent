"use client";

import { useKnowledgeGraph } from "@/features/knowledge-map/hooks/useKnowledgeGraph";
import { KnowledgeGraphCanvas } from "./KnowledgeGraphCanvas";

type KnowledgeGraphPanelProps = {
  focusLabel?: string;
  onJumpToChat: (question: string) => void;
  onJumpToQuestions: (topic: string) => void;
};

export default function KnowledgeGraphPanel({
  focusLabel = "",
  onJumpToChat,
  onJumpToQuestions,
}: KnowledgeGraphPanelProps) {
  const {
    nodes,
    edges,
    selectedNode,
    error,
    setSelectedNode,
    onNodesChange,
  } = useKnowledgeGraph(focusLabel);

  return (
    <div className="flex flex-col h-full">
      {focusLabel && (
        <div className="flex items-center justify-between border-b border-emerald-100 bg-emerald-50/70 px-5 py-2 text-sm text-emerald-900">
          <div>
            已从智能问答聚焦知识点：
            <span className="ml-1 font-semibold">{focusLabel}</span>
            <span className="ml-2 text-xs text-emerald-600">相关节点与一跳关系已高亮</span>
          </div>
        </div>
      )}
      <div className="flex min-h-0 flex-1 relative flex-row overflow-hidden bg-slate-50">
        <div className="flex h-full min-h-0 flex-1 min-w-0">
          <KnowledgeGraphCanvas
            nodes={nodes}
            edges={edges}
            error={error}
            selectedNodeId={selectedNode?.id}
            onSelectNode={setSelectedNode}
            onNodesChange={onNodesChange}
          />
        </div>

        {nodes.length > 0 && (
          <div className="pointer-events-none absolute bottom-4 left-4 z-10 rounded-xl border border-slate-200 bg-white/90 px-3.5 py-2.5 shadow-sm backdrop-blur-sm">
            <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400">关系图例</div>
            <div className="space-y-1.5 text-[11px] text-slate-600">
              <div className="flex items-center gap-2"><span className="h-0.5 w-5 rounded bg-slate-300" />包含关系</div>
              <div className="flex items-center gap-2"><span className="h-0.5 w-5 rounded bg-indigo-400" />前置依赖</div>
              <div className="flex items-center gap-2"><span className="w-5 border-t-2 border-dashed border-rose-300" />跨学科关联</div>
            </div>
          </div>
        )}

        {/* Selected Node Details Drawer (交互联动核心) */}
        {selectedNode && (
          <div className="w-[340px] border-l border-slate-200 bg-white shadow-xl flex flex-col h-full transform transition-all duration-300 relative z-10 shrink-0 select-none">
            {/* Header */}
            <div className="p-4 border-b border-slate-100 flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                {selectedNode.data.kind === "root" ? "⚡ 主干学科" : selectedNode.data.kind === "level1" ? "📂 核心章节" : "📌 细分考点"}
              </span>
              <button
                onClick={() => setSelectedNode(null)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-50 hover:text-slate-600 transition-colors"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 p-5 overflow-y-auto space-y-5">
              <div>
                <span className="inline-block rounded-full px-2.5 py-0.5 text-[10px] font-bold" style={{ background: `${selectedNode.data.accent}20`, color: selectedNode.data.accent }}>
                  {selectedNode.data.categoryLabel || selectedNode.data.category}
                </span>
                <h3 className="text-base font-bold text-slate-800 mt-2">
                  {selectedNode.data.label}
                </h3>
              </div>

              {selectedNode.data.childCount != null && selectedNode.data.childCount > 0 && (
                <div className="rounded-xl bg-slate-50 p-3 text-slate-600 border border-slate-100/50">
                  <span className="text-[10px] text-slate-400 block font-medium">子章节及考点数</span>
                  <span className="text-sm font-bold text-slate-800">{selectedNode.data.childCount} 个</span>
                </div>
              )}

              <div className="space-y-1">
                <span className="text-[10px] text-slate-400 block font-medium">考点简介</span>
                {selectedNode.data.description ? (
                  <p className="text-xs text-slate-600 leading-relaxed bg-slate-50 p-3 rounded-xl border border-slate-100/50">
                    {selectedNode.data.description}
                  </p>
                ) : (
                  <p className="text-xs text-slate-500 leading-relaxed bg-slate-50 p-3 rounded-xl border border-slate-100/50 italic">
                    暂无简介。本节点为 408 {selectedNode.data.categoryLabel} 统考大纲的核心部分，您可以点击下方按钮，快捷调遣 AI 导师深入精讲或在线组卷。
                  </p>
                )}
              </div>
            </div>

            {/* Action Buttons (Linkages) */}
            <div className="p-4 border-t border-slate-100 bg-slate-50/50 space-y-2">
              <button
                onClick={() => {
                  const q = `我想系统学习关于「${selectedNode.data.label}」（所属科目：${selectedNode.data.categoryLabel || selectedNode.data.category}）的内容，能为我详细剖析它的核心概念、历年考研重点以及高频常考题型吗？`;
                  onJumpToChat(q);
                }}
                className="w-full rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-2.5 text-xs shadow-md shadow-emerald-600/10 flex items-center justify-center gap-2 transition-all active:scale-95"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
                AI 智能提问此考点
              </button>

              <button
                onClick={() => {
                  onJumpToQuestions(selectedNode.data.label);
                }}
                className="w-full rounded-xl bg-[#FFF1E6] border border-[#FFD9B8] hover:bg-[#FFE6D0] text-[#C2410C] font-semibold py-2.5 text-xs flex items-center justify-center gap-2 transition-all active:scale-95"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
                </svg>
                生成此考点专项练习
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
