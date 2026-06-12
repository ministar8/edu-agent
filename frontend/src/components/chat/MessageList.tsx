import { memo, RefObject, useCallback } from "react";

import { useConversationTree } from "@/hooks/useConversationTree";
import type { ChatPanelState, Message } from "@/types/chat";
import { EmptyChatState } from "./EmptyChatState";
import { MessageBubble } from "./MessageBubble";
import { StreamingMessage } from "./StreamingMessage";

type MessageListProps = {
  messages: Message[];
  loading: boolean;
  streamingText: string;
  streamingAgent: string;
  activeTool: string | null;
  streamingGovernance: ChatPanelState["streamingGovernance"];
  statusLabel: string;
  activeLeafId: number | null;
  messagesEndRef: RefObject<HTMLDivElement>;
  onSelectSuggestion: (suggestion: string) => void;
  onOpenKnowledgeGraph?: (focus: string) => void;
  onGenerateSimilarPractice?: (topic: string) => void;
  onRegenerate?: () => void;
  onSetActiveLeafId?: (id: number | null) => void;
};

function MessageListComponent({
  messages,
  loading,
  streamingText,
  streamingAgent,
  activeTool,
  streamingGovernance,
  statusLabel,
  activeLeafId,
  messagesEndRef,
  onSelectSuggestion,
  onOpenKnowledgeGraph,
  onGenerateSimilarPractice,
  onRegenerate,
  onSetActiveLeafId,
}: MessageListProps) {
  const { activePath, getSiblings, getActiveSiblingIndex, switchBranch } = useConversationTree(messages, activeLeafId);

  const handleSwitchBranch = useCallback((msgId: number, direction: "prev" | "next") => {
    const newLeafId = switchBranch(msgId, direction);
    if (newLeafId != null && onSetActiveLeafId) {
      onSetActiveLeafId(newLeafId);
    }
  }, [switchBranch, onSetActiveLeafId]);

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {messages.length === 0 && !loading && <EmptyChatState onSelectSuggestion={onSelectSuggestion} />}

      {activePath.map((message, index) => {
        const previousUserMessage = [...activePath.slice(0, index)].reverse().find((item) => item.role === "user")?.content;
        const isLastAssistant = message.role === "assistant" && index === activePath.length - 1 && !loading;
        const msgId = message.id;
        const siblings = msgId != null ? getSiblings(msgId) : [];
        const siblingIndex = msgId != null ? getActiveSiblingIndex(msgId) : 0;
        const siblingCount = siblings.length;
        return (
          <MessageBubble
            key={msgId != null ? `msg-${msgId}` : `msg-${index}`}
            message={message}
            previousUserMessage={previousUserMessage}
            isLastAssistant={isLastAssistant}
            siblingIndex={siblingIndex}
            siblingCount={siblingCount}
            onOpenKnowledgeGraph={onOpenKnowledgeGraph}
            onGenerateSimilarPractice={onGenerateSimilarPractice}
            onRegenerate={isLastAssistant ? onRegenerate : undefined}
            onSwitchBranch={msgId != null && siblingCount > 1 ? (dir) => handleSwitchBranch(msgId, dir) : undefined}
          />
        );
      })}

      {loading && (
        <StreamingMessage
          streamingAgent={streamingAgent}
          activeTool={activeTool}
          streamingGovernance={streamingGovernance}
          streamingText={streamingText}
          statusLabel={statusLabel}
        />
      )}
      <div ref={messagesEndRef} />
    </div>
  );
}

export const MessageList = memo(MessageListComponent);
