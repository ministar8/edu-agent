"use client";

import { useCallback, useEffect, useState } from "react";
import { http } from "@/lib/http";
import { getBaseThreadId } from "@/lib/thread";
import type { ConversationItem } from "@/types/conversation";

type ConversationListProps = {
  activeThreadId: string;
  onSelect: (conv: ConversationItem) => void;
  onNewChat: () => void;
  refreshKey?: number;
};

export function ConversationList({ activeThreadId, onSelect, onNewChat, refreshKey }: ConversationListProps) {
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [loadError, setLoadError] = useState(false);

  const loadConversations = useCallback(async () => {
    try {
      const res = await http.get("/api/chat/conversations");
      setConversations(res.data || []);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadConversations();
  }, [refreshKey, loadConversations]);

  const handleDelete = useCallback(async (e: React.MouseEvent, convId: number) => {
    e.stopPropagation();
    if (deletingId === convId) return;
    setDeletingId(convId);
    try {
      await http.delete("/api/chat/conversations/" + convId);
      setConversations((prev) => prev.filter((c) => c.id !== convId));
    } catch (err) {
      console.error("[ConversationList] delete failed", err instanceof Error ? err.message : err);
    } finally {
      setDeletingId(null);
    }
  }, [deletingId]);

  return (
    <div className="flex flex-col h-full">
      <button onClick={onNewChat} className="mx-3 mt-3 mb-2 flex h-11 items-center gap-2 rounded-xl border border-dashed border-slate-300 px-3 text-sm text-slate-600 transition-colors hover:border-slate-400 hover:bg-slate-50">
        <span className="text-base">+</span>
        <span>新建对话</span>
      </button>
      <div className="flex-1 overflow-y-auto px-3 space-y-2">
        {loading ? (
          <div className="text-xs text-slate-400 text-center py-4">加载中...</div>
        ) : conversations.length === 0 ? (
          <div className="text-xs text-slate-400 text-center py-4">{loadError ? "加载失败，请刷新重试" : "暂无对话"}</div>
        ) : (
          conversations.map((conv) => {
            const isActive = getBaseThreadId(conv.thread_id) === activeThreadId || conv.thread_id === activeThreadId;
            const isDeleting = deletingId === conv.id;
            return (
              <div key={conv.id} onClick={() => onSelect(conv)} className={"group relative flex h-12 w-full cursor-pointer items-center rounded-xl border px-3 text-left transition-colors " + (isActive ? "border-emerald-200 bg-emerald-50" : "border-transparent hover:bg-stone-50")}>
                <div className={"text-sm truncate pr-6 " + (isActive ? "text-emerald-700 font-medium" : "text-stone-700")}>{conv.title || "新对话"}</div>
                <button onClick={(e) => handleDelete(e, conv.id)} disabled={isDeleting} className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-300 opacity-100 transition-opacity hover:bg-red-50 hover:text-red-500 md:opacity-0 md:group-hover:md:opacity-100 disabled:opacity-50" title="删除">
                  {isDeleting ? (
                    <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="12" /></svg>
                  ) : (
                    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
                  )}
                </button>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
