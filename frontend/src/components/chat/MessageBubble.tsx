import { memo } from "react";

import type { Message } from "@/types/chat";
import { agentColors, agentLabels } from "./chatMeta";
import { FormattedMessage } from "./FormattedMessage";
import { GovernanceBadge } from "./GovernanceBadge";
import { SourceList } from "./SourceList";

type MessageBubbleProps = {
  message: Message;
};

function MessageBubbleComponent({ message }: MessageBubbleProps) {
  return (
    <div className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[70%] rounded-xl px-4 py-3 ${
          message.role === "user"
            ? "chat-message-user"
            : agentColors[message.agentName || ""] || "chat-message-agent"
        }`}
      >
        {message.agentName && message.role === "assistant" && (
          <div className="text-xs font-medium text-slate-500 mb-1 flex items-center gap-2">
            <span>{agentLabels[message.agentName] || message.agentName}</span>
            {message.governance && <GovernanceBadge governance={message.governance} />}
          </div>
        )}
        {message.role === "assistant" ? (
          <FormattedMessage content={message.content} />
        ) : (
          <div className="whitespace-pre-wrap text-sm leading-7">{message.content}</div>
        )}
        {message.sources && <SourceList sources={message.sources} />}
      </div>
    </div>
  );
}

export const MessageBubble = memo(MessageBubbleComponent);
