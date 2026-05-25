import { useCallback, useRef } from "react";

import { API_BASE_URL } from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";
import { getAuthHeaders, notifyUnauthorized } from "@/lib/http";
import type { ChatPanelState, Governance, Message } from "@/types/chat";
import type { ConversationDetail } from "@/types/conversation";

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

function getBaseThreadId(threadId: string): string {
  return threadId.includes(":") ? threadId.split(":").slice(1).join(":") : threadId;
}

export function useChatStream({ token, state, setState }: UseChatStreamParams) {
  const stateRef = useRef(state);
  const streamStateByThreadRef = useRef<Map<string, ChatPanelState>>(new Map());
  const abortRef = useRef<AbortController | null>(null);
  stateRef.current = state;

  const updateState = useCallback((patch: Partial<ChatPanelState>) => {
    setState((prev) => ({ ...prev, ...patch }));
  }, [setState]);

  const updateThreadState = useCallback((threadId: string, patch: Partial<ChatPanelState>) => {
    const baseThreadId = getBaseThreadId(threadId);
    const cached = streamStateByThreadRef.current.get(baseThreadId) ?? streamStateByThreadRef.current.get(threadId);
    if (cached) {
      const nextCached = { ...cached, ...patch };
      streamStateByThreadRef.current.set(baseThreadId, nextCached);
      if (threadId !== baseThreadId) streamStateByThreadRef.current.set(threadId, nextCached);
    }

    setState((prev) => {
      if (getBaseThreadId(prev.baseThreadId) !== baseThreadId) return prev;
      const next = { ...prev, ...patch };
      stateRef.current = next;
      return next;
    });
  }, [setState]);

  const sendMessage = useCallback(async () => {
    const { input, loading, baseThreadId } = stateRef.current;
    const requestThreadId = baseThreadId;

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

    const pendingState: ChatPanelState = {
      ...stateRef.current,
      messages: [...stateRef.current.messages, userMsg],
      input: "",
      loading: true,
      streamingText: "",
      streamingAgent: "supervisor",
      activeTool: null,
      streamingGovernance: null,
    };
    streamStateByThreadRef.current.set(requestThreadId, pendingState);
    stateRef.current = pendingState;
    setState((prev) => prev.baseThreadId === requestThreadId ? pendingState : prev);

    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    try {
      const res = await fetch(`${API_BASE_URL}/api/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({ message: userContent, thread_id: requestThreadId }),
        signal: ac.signal,
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
        if (done || ac.signal.aborted) break;

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
              updateThreadState(requestThreadId, { streamingAgent: agentName });
            }

            if (typeof data.text === "string") {
              fullText += data.text;
              updateThreadState(requestThreadId, { streamingText: fullText });
            }

            if (typeof data.final_answer === "string") {
              fullText = data.final_answer;
              updateThreadState(requestThreadId, { streamingText: fullText });
            }

            if (Array.isArray(data.sources)) {
              latestSources = data.sources.filter((source): source is string => typeof source === "string");
            }

            if (typeof data.tool_name === "string") {
              updateThreadState(requestThreadId, { activeTool: data.status === "start" ? data.tool_name : null });
            }

            if (data.confidence !== undefined) {
              const governance = toGovernance(data);
              latestGovernance = governance;
              updateThreadState(requestThreadId, { streamingGovernance: governance });
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
      const cached = streamStateByThreadRef.current.get(requestThreadId) ?? stateRef.current;
      const completedState = {
        ...cached,
        messages: [...cached.messages, assistantMsg],
        loading: false,
        streamingText: "",
        streamingAgent: "",
        activeTool: null,
        streamingGovernance: null,
      };
      streamStateByThreadRef.current.set(requestThreadId, completedState);
      stateRef.current = stateRef.current.baseThreadId === requestThreadId ? completedState : stateRef.current;
      setState((prev) => prev.baseThreadId === requestThreadId ? completedState : prev);
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === "AbortError") {
        // Aborted by new message or unmount — not a real error
        return;
      }
      const msg = getErrorMessage(error, "聊天请求失败");
      const errorMsg: Message = {
        role: "assistant",
        content: `系统错误: ${msg}`,
        agentName: "system",
        timestamp: new Date(),
      };
      const cached = streamStateByThreadRef.current.get(requestThreadId) ?? stateRef.current;
      const failedState = { ...cached, messages: [...cached.messages, errorMsg] };
      streamStateByThreadRef.current.set(requestThreadId, failedState);
      stateRef.current = stateRef.current.baseThreadId === requestThreadId ? failedState : stateRef.current;
      setState((prev) => prev.baseThreadId === requestThreadId ? failedState : prev);
    } finally {
      updateThreadState(requestThreadId, {
        loading: false, streamingText: "", streamingAgent: "",
        activeTool: null, streamingGovernance: null,
      });
    }
  }, [setState, token, updateThreadState]);

  const loadConversation = useCallback(async (conversationId: number) => {
    if (!token) return;
    try {
    const res = await fetch(`${API_BASE_URL}/api/chat/conversations/${conversationId}`, {
      headers: { ...getAuthHeaders() },
    });
    if (!res.ok) { if (res.status === 401) notifyUnauthorized(); return; }
    const detail: ConversationDetail = await res.json();
    const msgs: Message[] = detail.messages.map((m) => ({
      role: m.role, content: m.content,
      agentName: m.agent_name ?? undefined, sources: m.sources,
      governance: m.governance && typeof m.governance === "object" ? toGovernance(m.governance as Record<string, unknown>) : undefined,
      timestamp: new Date(m.created_at),
    }));
    const baseThread = getBaseThreadId(detail.thread_id);
    const cachedStreamingState = streamStateByThreadRef.current.get(baseThread)
      ?? streamStateByThreadRef.current.get(detail.thread_id)
      ?? Array.from(streamStateByThreadRef.current.values()).find((cached) => (
        cached.loading
        && (cached.conversationId === detail.id || getBaseThreadId(cached.baseThreadId) === baseThread)
      ));
    // SSE still streaming → restore live state
    if (cachedStreamingState?.loading) {
      const restoredState = { ...cachedStreamingState, baseThreadId: baseThread, conversationId: detail.id };
      stateRef.current = restoredState;
      setState(restoredState);
      return;
    }
    // SSE finished but cache has more messages than DB (race condition) → prefer cache
    if (cachedStreamingState && cachedStreamingState.messages.length > msgs.length) {
      const mergedState = { ...cachedStreamingState, loading: false, streamingText: "", streamingAgent: "", activeTool: null, streamingGovernance: null, baseThreadId: baseThread, conversationId: detail.id };
      stateRef.current = mergedState;
      setState(mergedState);
      return;
    }
    const loadedState = { messages: msgs, input: "", loading: false, streamingText: "", streamingAgent: "", activeTool: null, streamingGovernance: null, baseThreadId: baseThread, conversationId: detail.id };
    stateRef.current = loadedState;
    setState(loadedState);
    } catch {
      // Load conversation failed — non-critical
    }
  }, [setState, token]);

  const newChat = useCallback(() => {
    const nextState = { messages: [], input: "", loading: false, streamingText: "", streamingAgent: "", activeTool: null, streamingGovernance: null, baseThreadId: `session-${Date.now()}-${Math.random().toString(36).slice(2)}`, conversationId: null };
    stateRef.current = nextState;
    setState(nextState);
  }, [setState]);

  return { state, sendMessage, updateState, loadConversation, newChat };
}
