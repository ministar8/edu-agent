import { useCallback, useRef } from "react";

import { API_BASE_URL } from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";
import { getAuthHeaders, notifyUnauthorized } from "@/lib/http";
import type { ChatPanelState, Governance, Message } from "@/types/chat";

type UseChatStreamParams = {
  token: string | null;
  state: ChatPanelState;
  setState: React.Dispatch<React.SetStateAction<ChatPanelState>>;
};

function toGovernance(data: Record<string, unknown>): Governance {
  return {
    confidence: typeof data.confidence === "string" ? data.confidence : "unknown",
    has_source: typeof data.has_source === "boolean" ? data.has_source : false,
    passed: typeof data.passed === "boolean" ? data.passed : true,
    flags: Array.isArray(data.flags) ? data.flags.filter((flag): flag is string => typeof flag === "string") : [],
  };
}

export function useChatStream({ token, state, setState }: UseChatStreamParams) {
  const stateRef = useRef(state);
  stateRef.current = state;

  const updateState = useCallback((patch: Partial<ChatPanelState>) => {
    setState((prev) => ({ ...prev, ...patch }));
  }, [setState]);

  const sendMessage = useCallback(async () => {
    const { input, loading, threadId } = stateRef.current;

    if (!token) {
      setState((prev) => ({
        ...prev,
        messages: [
          ...prev.messages,
          {
            role: "assistant",
            content: "登录状态已失效，请重新登录后再试。",
            agentName: "system",
            timestamp: new Date(),
          },
        ],
      }));
      return;
    }

    if (!input.trim() || loading) return;

    const userContent = input;
    const userMsg: Message = {
      role: "user",
      content: userContent,
      timestamp: new Date(),
    };

    setState((prev) => ({
      ...prev,
      messages: [...prev.messages, userMsg],
      input: "",
      loading: true,
      streamingText: "",
      streamingAgent: "supervisor",
      activeTool: null,
      streamingGovernance: null,
    }));

    try {
      const res = await fetch(`${API_BASE_URL}/api/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({ message: userContent, thread_id: threadId }),
      });

      if (!res.ok || !res.body) {
        if (res.status === 401) {
          notifyUnauthorized();
          throw new Error("登录状态已失效，请重新登录");
        }
        throw new Error(`HTTP ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let eventType = "";
      let agentName = "supervisor";
      let fullText = "";
      let latestGovernance: Governance | null = null;
      let latestSources: string[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
            continue;
          }
          if (!line.startsWith("data: ")) continue;

          let data: Record<string, unknown>;
          try {
            data = JSON.parse(line.slice(6));
          } catch {
            continue;
          }

          if (eventType === "error") {
            throw new Error(typeof data.message === "string" ? data.message : "流式响应失败");
          }

          try {
            if (typeof data.agent_name === "string") {
              agentName = data.agent_name;
              updateState({ streamingAgent: agentName });
            }

            if (typeof data.text === "string") {
              fullText += data.text;
              updateState({ streamingText: fullText });
            }

            if (typeof data.final_answer === "string") {
              fullText = data.final_answer;
              updateState({ streamingText: fullText });
            }

            if (Array.isArray(data.sources)) {
              latestSources = data.sources.filter((source): source is string => typeof source === "string");
            }

            if (typeof data.tool_name === "string") {
              updateState({ activeTool: data.status === "start" ? data.tool_name : null });
            }

            if (data.confidence !== undefined) {
              const governance = toGovernance(data);
              latestGovernance = governance;
              updateState({ streamingGovernance: governance });
            }
          } catch {
            // Non-critical: skip malformed SSE data lines
          } finally {
            eventType = "";
          }
        }
      }

      const assistantMsg: Message = {
        role: "assistant",
        content: fullText,
        agentName,
        sources: latestSources,
        governance: latestGovernance ?? undefined,
        timestamp: new Date(),
      };

      setState((prev) => ({
        ...prev,
        messages: [...prev.messages, assistantMsg],
      }));
    } catch (error: unknown) {
      const msg = getErrorMessage(error, "聊天请求失败");
      const errorMsg: Message = {
        role: "assistant",
        content: `系统错误: ${msg}`,
        agentName: "system",
        timestamp: new Date(),
      };
      setState((prev) => ({
        ...prev,
        messages: [...prev.messages, errorMsg],
      }));
    } finally {
      updateState({
        loading: false,
        streamingText: "",
        streamingAgent: "",
        activeTool: null,
        streamingGovernance: null,
      });
    }
  }, [setState, token, updateState]);

  return { sendMessage, updateState };
}
