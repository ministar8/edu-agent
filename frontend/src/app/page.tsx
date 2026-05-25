"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Sidebar } from "@/components/app-shell/Sidebar";
import { WorkspaceContent } from "@/components/app-shell/WorkspaceContent";
import { WorkspaceHeader } from "@/components/app-shell/WorkspaceHeader";
import { useAuth } from "@/lib/auth";
import type { ChatPanelState } from "@/types/chat";
import type { TabType } from "@/types/navigation";
import type { QuestionPanelState } from "@/types/question";

export default function Home() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<TabType>("chat");
  const [questionState, setQuestionState] = useState<QuestionPanelState>({
    topic: "",
    count: 1,
    difficulty: "mixed",
    loading: false,
    result: "",
    resultTopic: "",
    questions: [],
    batchId: null,
    wrongQuestions: [],
    wrongLoading: false,
    activeTab: "generate",
  });
  const [chatState, setChatState] = useState<ChatPanelState>({
    messages: [],
    input: "",
    loading: false,
    streamingText: "",
    streamingAgent: "",
    activeTool: null,
    streamingGovernance: null,
    baseThreadId: `session-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    conversationId: null,
  });

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#f4f6fb]">
        <div className="flex items-center gap-3 text-slate-400">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-emerald-400 border-t-transparent" />
          <span className="text-sm">加载中...</span>
        </div>
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="flex h-screen gap-4 bg-stone-50 p-4">
      <Sidebar activeTab={activeTab} user={user} onTabChange={setActiveTab} onLogout={logout} />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-stone-200/60 bg-white shadow-sm">
        <WorkspaceHeader activeTab={activeTab} />
        <WorkspaceContent
          activeTab={activeTab}
          chatState={chatState}
          setChatState={setChatState}
          questionState={questionState}
          setQuestionState={setQuestionState}
        />
      </div>
    </div>
  );
}
