import { memo } from "react";

import type { Governance } from "@/types/chat";
import { agentColors, agentLabels, toolLabels } from "./chatMeta";
import { FormattedMessage } from "./FormattedMessage";
import { GovernanceBadge } from "./GovernanceBadge";

type StreamingMessageProps = {
  streamingAgent: string;
  activeTool: string | null;
  streamingGovernance: Governance | null;
  streamingText: string;
};

function StreamingMessageComponent({ streamingAgent, activeTool, streamingGovernance, streamingText }: StreamingMessageProps) {
  return (
    <div className="flex justify-start">
      <div className={`max-w-[70%] rounded-xl px-4 py-3 ${agentColors[streamingAgent] || "chat-message-agent"}`}>
        {streamingAgent && (
          <div className="text-xs font-medium text-slate-500 mb-1 flex items-center gap-2">
            <span>{agentLabels[streamingAgent] || streamingAgent}</span>
            {streamingGovernance && <GovernanceBadge governance={streamingGovernance} />}
          </div>
        )}

        {activeTool && (
          <div className="text-xs text-blue-500 mb-2 flex items-center gap-1">
            <span className="animate-spin">⚙</span>
            {toolLabels[activeTool] || activeTool}...
          </div>
        )}
        {streamingText ? (
          <div>
            <FormattedMessage content={streamingText} />
            <span className="animate-pulse text-slate-500">▌</span>
          </div>
        ) : (
          <div className="text-sm text-slate-500">
            <span className="inline-flex gap-1">
              <span className="animate-bounce">●</span>
              <span className="animate-bounce" style={{ animationDelay: "0.1s" }}>●</span>
              <span className="animate-bounce" style={{ animationDelay: "0.2s" }}>●</span>
            </span>
            {" "}Agent正在思考...
          </div>
        )}
      </div>
    </div>
  );
}

export const StreamingMessage = memo(StreamingMessageComponent);
