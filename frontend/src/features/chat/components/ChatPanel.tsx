"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "@/shared/lib/auth";
import { useChatStream } from "@/features/chat/hooks/useChatStream";
import { IconGraduation } from "@/shared/ui/icons";
import type { ChatPanelState } from "@/shared/types/chat";
import type { ConversationItem } from "@/shared/types/conversation";
import { ChatInput } from "./ChatInput";
import { chatSuggestions } from "./chatMeta";
import { ConversationList } from "./ConversationList";
import { MessageList } from "./MessageList";

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 6) return "夜深了";
  if (hour < 11) return "早上好";
  if (hour < 13) return "中午好";
  if (hour < 18) return "下午好";
  return "晚上好";
}

type ChatPanelProps = {
  state: ChatPanelState;
  setState: React.Dispatch<React.SetStateAction<ChatPanelState>>;
  onOpenKnowledgeGraph?: (focus: string) => void;
  onGenerateSimilarPractice?: (topic: string) => void;
};

export default function ChatPanel({ state, setState, onOpenKnowledgeGraph, onGenerateSimilarPractice }: ChatPanelProps) {
  const { user } = useAuth();
  const { sendMessage, stop, regenerate, updateState, loadConversation, newChat } = useChatStream({ authenticated: !!user, state, setState });
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [convRefreshKey, setConvRefreshKey] = useState(0);

  const handleSelectSuggestion = useCallback((suggestion: string) => {
    updateState({ input: suggestion });
  }, [updateState]);

  const handleInputChange = useCallback((value: string) => {
    updateState({ input: value });
  }, [updateState]);

  const handleSelectConversation = useCallback(async (conv: ConversationItem) => {
    await loadConversation(conv.id);
  }, [loadConversation]);

  const handleNewChat = useCallback(() => {
    newChat();
  }, [newChat]);

  const prevMsgCount = useRef(state.messages.length);
  useEffect(() => {
    if (state.messages.length > prevMsgCount.current && !state.loading) {
      setConvRefreshKey((k) => k + 1);
    }
    prevMsgCount.current = state.messages.length;
  }, [state.messages.length, state.loading]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [state.messages, state.streamingText]);

  const isEmpty = state.messages.length === 0 && !state.loading;

  return (
    <div className="flex h-full">
      <div className="w-[220px] shrink-0 border-r border-stone-200/60 bg-stone-50/50">
        <ConversationList
          activeThreadId={state.baseThreadId}
          onSelect={handleSelectConversation}
          onNewChat={handleNewChat}
          refreshKey={convRefreshKey}
        />
      </div>
      <div className="flex flex-1 flex-col min-w-0">
        {isEmpty ? (
          <div className="flex flex-1 flex-col items-center justify-center px-4 pb-12">
            <div className="w-full max-w-3xl">
              <div className="mb-8 flex flex-col items-center text-center">
                <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-600 text-white shadow-sm">
                  <IconGraduation size={26} />
                </div>
                <h2 className="text-3xl font-semibold tracking-tight text-slate-800">
                  {getGreeting()}{user?.display_name ? `，${user.display_name}` : ""}
                </h2>
                <p className="mt-2 text-sm text-slate-400">有什么可以帮你的？</p>
              </div>
              <ChatInput
                input={state.input}
                loading={state.loading}
                onInputChange={handleInputChange}
                onSubmit={() => void sendMessage()}
                onStop={() => stop()}
                variant="centered"
              />
              <div className="mx-auto mt-4 flex max-w-3xl flex-wrap justify-center gap-2 px-4">
                {chatSuggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => handleSelectSuggestion(suggestion)}
                    className="rounded-full border border-stone-200/80 bg-white px-3.5 py-1.5 text-[13px] text-stone-600 shadow-sm transition hover:border-emerald-200 hover:bg-emerald-50/50 hover:text-emerald-700"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <>
            <MessageList
              messages={state.messages}
              loading={state.loading}
              streamingText={state.streamingText}
              streamingAgent={state.streamingAgent}
              activeTool={state.activeTool}
              streamingGovernance={state.streamingGovernance}
              statusLabel={state.statusLabel}
              activeLeafId={state.activeLeafId}
              messagesEndRef={messagesEndRef}
              onSelectSuggestion={handleSelectSuggestion}
              onOpenKnowledgeGraph={onOpenKnowledgeGraph}
              onGenerateSimilarPractice={onGenerateSimilarPractice}
              onRegenerate={() => void regenerate()}
              onSetActiveLeafId={(id) => updateState({ activeLeafId: id })}
            />
            <ChatInput
              input={state.input}
              loading={state.loading}
              onInputChange={handleInputChange}
              onSubmit={() => void sendMessage()}
              onStop={() => stop()}
            />
          </>
        )}
      </div>
    </div>
  );
}
