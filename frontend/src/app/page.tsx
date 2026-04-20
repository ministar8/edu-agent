"use client";

import { useState } from "react";
import AgentFlow from "@/components/AgentFlow";
import ChatPanel from "@/components/ChatPanel";
import KnowledgePanel from "@/components/KnowledgePanel";
import RAGProcessPanel from "@/components/RAGProcessPanel";
import KnowledgeGraphPanel from "@/components/KnowledgeGraphPanel";
import QuestionPanel from "@/components/QuestionPanel";

type TabType = "chat" | "questions" | "agents" | "knowledge" | "rag" | "kgraph";

const tabs: { id: TabType; label: string; icon: string }[] = [
  { id: "chat", label: "智能问答", icon: "💬" },
  { id: "questions", label: "题目生成", icon: "📝" },
  { id: "agents", label: "Agent协作", icon: "🤖" },
  { id: "knowledge", label: "知识库管理", icon: "📚" },
  { id: "rag", label: "RAG过程", icon: "🔍" },
  { id: "kgraph", label: "知识图谱", icon: "🕸️" },
];

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabType>("chat");

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <header className="bg-gradient-to-r from-blue-600 to-purple-600 text-white px-6 py-4 shadow-lg">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">智能教学辅导多Agent系统</h1>
            <p className="text-blue-100 text-sm mt-1">
              LangChain + LangGraph | RAG + 知识图谱
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="bg-green-500 text-white text-xs px-2 py-1 rounded-full">
              系统在线
            </span>
          </div>
        </div>
      </header>

      {/* Tab Navigation */}
      <nav className="bg-white border-b px-6 flex gap-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            <span className="mr-1">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Main Content */}
      <main className="flex-1 overflow-hidden">
        {activeTab === "chat" && <ChatPanel />}
        {activeTab === "questions" && <QuestionPanel />}
        {activeTab === "agents" && <AgentFlow />}
        {activeTab === "knowledge" && <KnowledgePanel />}
        {activeTab === "rag" && <RAGProcessPanel />}
        {activeTab === "kgraph" && <KnowledgeGraphPanel />}
      </main>
    </div>
  );
}
