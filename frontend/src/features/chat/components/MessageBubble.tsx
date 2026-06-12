import { memo } from "react";

import type { Message } from "@/shared/types/chat";
import { agentColors, agentLabels } from "./chatMeta";
import { BranchNavigator } from "./BranchNavigator";
import { FormattedMessage } from "./FormattedMessage";
import { GovernanceBadge } from "./GovernanceBadge";
import { SourceList } from "./SourceList";
import { TeachingAnalysisPanel } from "./TeachingAnalysisPanel";

type MessageBubbleProps = {
  message: Message;
  previousUserMessage?: string;
  isLastAssistant?: boolean;
  siblingIndex?: number;
  siblingCount?: number;
  onOpenKnowledgeGraph?: (focus: string) => void;
  onGenerateSimilarPractice?: (topic: string) => void;
  onRegenerate?: () => void;
  onSwitchBranch?: (direction: "prev" | "next") => void;
};

function MessageBubbleComponent({
  message, previousUserMessage, isLastAssistant,
  siblingIndex, siblingCount,
  onOpenKnowledgeGraph, onGenerateSimilarPractice,
  onRegenerate, onSwitchBranch,
}: MessageBubbleProps) {
  const showTeachingAnalysis = message.role === "assistant" && message.agentName !== "system" && message.content.trim().length > 0;

  return (
    <div className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
      <div
        className={`${message.role === "assistant" ? "max-w-[86%]" : "max-w-[70%]"} rounded-xl px-4 py-3 ${
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
        {message.sources && !showTeachingAnalysis && <SourceList sources={message.sources} />}
        {siblingCount != null && siblingCount > 1 && onSwitchBranch && (
          <BranchNavigator
            currentIndex={siblingIndex ?? 0}
            totalCount={siblingCount}
            onPrev={() => onSwitchBranch("prev")}
            onNext={() => onSwitchBranch("next")}
          />
        )}
        {isLastAssistant && onRegenerate && (
          <button
            onClick={onRegenerate}
            className="mt-2 inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
            aria-label="重新生成"
          >
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="1 4 1 10 7 10" />
              <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
            </svg>
            重新生成
          </button>
        )}
        {showTeachingAnalysis && (
          <TeachingAnalysisPanel
            query={previousUserMessage}
            answer={message.content}
            agentName={message.agentName}
            sources={message.sources}
            governance={message.governance}
            agentSteps={message.agentSteps}
            onOpenKnowledgeGraph={onOpenKnowledgeGraph}
            onGenerateSimilarPractice={onGenerateSimilarPractice}
          />
        )}
      </div>
    </div>
  );
}

export const MessageBubble = memo(MessageBubbleComponent);
