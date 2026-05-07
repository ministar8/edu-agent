import { memo, RefObject } from "react";

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
  messagesEndRef: RefObject<HTMLDivElement>;
  onSelectSuggestion: (suggestion: string) => void;
};

function MessageListComponent({
  messages,
  loading,
  streamingText,
  streamingAgent,
  activeTool,
  streamingGovernance,
  messagesEndRef,
  onSelectSuggestion,
}: MessageListProps) {
  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {messages.length === 0 && !loading && <EmptyChatState onSelectSuggestion={onSelectSuggestion} />}

      {messages.map((message, index) => (
        <MessageBubble key={`${message.role}-${message.timestamp.getTime()}-${index}`} message={message} />
      ))}

      {loading && (
        <StreamingMessage
          streamingAgent={streamingAgent}
          activeTool={activeTool}
          streamingGovernance={streamingGovernance}
          streamingText={streamingText}
        />
      )}
      <div ref={messagesEndRef} />
    </div>
  );
}

export const MessageList = memo(MessageListComponent);
