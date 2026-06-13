"use client";

import { useState } from "react";

import { AgentFlow } from "@/features/agent-flow";
import { KnowledgePanel } from "@/features/knowledge-base";
import { RAGProcessPanel } from "@/features/rag-process";

type DebugView = "knowledge" | "agents" | "rag";

const debugViews: { id: DebugView; label: string; description: string }[] = [
  { id: "knowledge", label: "知识库管理", description: "上传、查看和维护索引集合" },
  { id: "agents", label: "Agent 协作流程", description: "查看 LangGraph 调度和 Agent 活动" },
  { id: "rag", label: "RAG 检索过程", description: "分析检索、rerank 与 KG trace" },
];

export default function DebugPanel() {
  const [activeView, setActiveView] = useState<DebugView>("knowledge");

  return (
    <div className="flex h-full flex-col bg-stone-50">
      <div className="border-b border-slate-200 bg-white px-6 py-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">管理调试</p>
            <h2 className="mt-2 text-lg font-semibold text-slate-900">技术能力入口已降级到这里</h2>
            <p className="mt-1 text-sm text-slate-500">学习用户优先使用工作台、问答、练习和知识地图；这里保留知识库、Agent 与 RAG 过程视图。</p>
          </div>
          <div className="flex rounded-2xl bg-slate-100 p-1">
            {debugViews.map((view) => (
              <button
                key={view.id}
                onClick={() => setActiveView(view.id)}
                className={`rounded-xl px-3 py-2 text-xs font-medium transition ${
                  activeView === view.id ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"
                }`}
              >
                {view.label}
              </button>
            ))}
          </div>
        </div>
        <div className="mt-3 text-xs text-slate-400">
          {debugViews.find((view) => view.id === activeView)?.description}
        </div>
      </div>
      <div className="min-h-0 flex-1 h-full">
        {activeView === "knowledge" && <KnowledgePanel />}
        {activeView === "agents" && <AgentFlow />}
        {activeView === "rag" && <RAGProcessPanel />}
      </div>
    </div>
  );
}
