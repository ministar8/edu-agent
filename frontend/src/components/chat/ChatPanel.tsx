"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "@/lib/auth";
import { useChatStream } from "@/hooks/useChatStream";
import type { ChatPanelState } from "@/types/chat";
import type { ConversationItem } from "@/types/conversation";
import { ChatInput } from "./ChatInput";
import { ConversationList } from "./ConversationList";
import { MessageList } from "./MessageList";

type ChatPanelProps = {
  state: ChatPanelState;
  setState: React.Dispatch<React.SetStateAction<ChatPanelState>>;
};

export default function ChatPanel({ state, setState }: ChatPanelProps) {
  const { token } = useAuth();
  const { sendMessage, updateState, loadConversation, newChat } = useChatStream({ token, state, setState });
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
        <MessageList
          messages={state.messages}
          loading={state.loading}
          streamingText={state.streamingText}
          streamingAgent={state.streamingAgent}
          activeTool={state.activeTool}
          streamingGovernance={state.streamingGovernance}
          messagesEndRef={messagesEndRef}
          onSelectSuggestion={handleSelectSuggestion}
        />
        <ChatInput
          input={state.input}
          loading={state.loading}
          onInputChange={handleInputChange}
          onSubmit={() => void sendMessage()}
        />
      </div>
    </div>
  );
}
