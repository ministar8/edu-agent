"use client";

import { Component, type ReactNode, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Sidebar } from "@/components/app-shell/Sidebar";
import { WorkspaceContent } from "@/components/app-shell/WorkspaceContent";
import { WorkspaceHeader } from "@/components/app-shell/WorkspaceHeader";
import { useAuth } from "@/lib/auth";
import { generateThreadId } from "@/lib/thread";
import type { ChatPanelState } from "@/types/chat";
import type { TabType } from "@/types/navigation";
import type { QuestionPanelState } from "@/types/question";

class ErrorBoundary extends Component<{ children: ReactNode; fallback?: ReactNode }, { hasError: boolean; errorMsg: string }> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, errorMsg: "" };
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, errorMsg: error.message };
  }
  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="flex h-screen items-center justify-center bg-stone-50">
          <div className="text-center">
            <p className="text-slate-500 text-sm mb-2">页面加载出错</p>
            <p className="text-slate-400 text-xs">{this.state.errorMsg}</p>
            <button onClick={() => this.setState({ hasError: false })} className="mt-3 text-xs text-emerald-600 underline">重试</button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

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
    statusLabel: "",
    baseThreadId: generateThreadId(),
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
    <ErrorBoundary>
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
    </ErrorBoundary>
  );
}
