"use client";

import { useCallback, useEffect, useRef } from "react";

import { useAuth } from "@/lib/auth";
import { useChatStream } from "@/hooks/useChatStream";
import type { ChatPanelProps } from "@/types/chat";
import { ChatInput } from "./ChatInput";
import { MessageList } from "./MessageList";

export default function ChatPanel({ state, setState }: ChatPanelProps) {
  const { token } = useAuth();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { sendMessage, updateState } = useChatStream({ token, state, setState });

  const handleSelectSuggestion = useCallback((suggestion: string) => {
    updateState({ input: suggestion });
  }, [updateState]);

  const handleInputChange = useCallback((value: string) => {
    updateState({ input: value });
  }, [updateState]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [state.messages, state.streamingText]);

  return (
    <div className="flex flex-col h-full">
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
  );
}
