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
  });
  const [chatState, setChatState] = useState<ChatPanelState>({
    messages: [],
    input: "",
    loading: false,
    streamingText: "",
    streamingAgent: "",
    activeTool: null,
    streamingGovernance: null,
    threadId: `session-${Date.now()}-${Math.random().toString(36).slice(2)}`,
  });

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-slate-500">加载中...</div>
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <div className="flex h-screen bg-[#eef3f8] p-4 text-slate-800">
      <Sidebar activeTab={activeTab} user={user} onTabChange={setActiveTab} onLogout={logout} />
      <div className="ml-4 flex min-w-0 flex-1 flex-col rounded-[28px] border border-slate-200 bg-white shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
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
