import { useCallback, useEffect, useRef } from "react";

import { useAgentActivity } from "@/shared/contexts/AgentActivityContext";
import { useTrackingRefresh } from "@/shared/contexts/TrackingRefreshContext";
import { API_BASE_URL } from "@/shared/lib/api";
import { getErrorMessage } from "@/shared/lib/errors";
import { getAuthHeaders, notifyUnauthorized } from "@/shared/lib/http";
import { getBaseThreadId, generateThreadId } from "@/shared/lib/thread";
import type { AgentStep, ChatPanelState, Governance, Message } from "@/shared/types/chat";
import type { ConversationDetail } from "@/shared/types/conversation";
import { parseStreamEvents, toAgentSteps, toGovernance } from "../lib/streamEvents";

type UseChatStreamParams = {
  authenticated: boolean;
  state: ChatPanelState;
  setState: React.Dispatch<React.SetStateAction<ChatPanelState>>;
};

const MAX_CACHED_THREADS = 20;

type StreamTerminalState = Pick<ChatPanelState, "loading" | "streamingText" | "streamingAgent" | "activeTool" | "streamingGovernance" | "statusLabel">;

const CLEARED_STREAM: StreamTerminalState = {
  loading: false, streamingText: "", streamingAgent: "", activeTool: null, streamingGovernance: null, statusLabel: "",
};

function finalizeThreadState(cached: ChatPanelState, msg: Message): ChatPanelState {
  return { ...cached, messages: [...cached.messages, msg], ...CLEARED_STREAM };
}

function getLastUserMessageId(messages: Message[]): number | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role === "user" && typeof message.id === "number") {
      return message.id;
    }
  }
  return null;
}

export function useChatStream({ authenticated, state, setState }: UseChatStreamParams) {
  const { setActiveAgent, setStatusLabel, setActiveTool, setStreaming, reset: resetActivity } = useAgentActivity();
  const { triggerRefresh: triggerTrackingRefresh } = useTrackingRefresh();
  const stateRef = useRef(state);
  const streamStateByThreadRef = useRef<Map<string, ChatPanelState>>(new Map());
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const localMessageIdRef = useRef(-Date.now());
  stateRef.current = state;

  // Cleanup on unmount: abort stream, clear timers
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

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

  // Evict oldest entries when cache exceeds limit
  const evictCache = useCallback(() => {
    const map = streamStateByThreadRef.current;
    if (map.size > MAX_CACHED_THREADS) {
      const keys = Array.from(map.keys());
      const toDelete = keys.slice(0, map.size - MAX_CACHED_THREADS);
      toDelete.forEach((k) => map.delete(k));
    }
  }, []);

  const nextLocalMessageId = useCallback(() => {
    localMessageIdRef.current -= 1;
    return localMessageIdRef.current;
  }, []);

  const sendMessage = useCallback(async (parentMessageId?: number | null) => {
    const { input, loading, baseThreadId } = stateRef.current;

    if (!authenticated) {
      setState((prev) => ({
        ...prev,
        messages: [
          ...prev.messages,
          { id: nextLocalMessageId(), role: "assistant", content: "登录状态已失效，请重新登录后再试。", agentName: "system", parentId: null, siblingsOrder: 0, childCount: 0, timestamp: new Date() },
        ],
      }));
      return;
    }

    if (!input.trim() || loading) return;

    // Temporary negative id until backend responds with real id via SSE done event
    const tempId = nextLocalMessageId();
    const userMsg: Message = {
      id: tempId, role: "user", content: input,
      parentId: parentMessageId ?? null, siblingsOrder: 0, childCount: 0,
      timestamp: new Date(),
    };

    const pendingState: ChatPanelState = {
      ...stateRef.current,
      messages: [...stateRef.current.messages, userMsg],
      input: "", loading: true, streamingText: "", streamingAgent: "supervisor",
      activeTool: null, streamingGovernance: null, statusLabel: "",
    };
    setActiveAgent("supervisor");
    setStatusLabel("正在分析问题...");
    streamStateByThreadRef.current.set(baseThreadId, pendingState);
    evictCache();
    stateRef.current = pendingState;
    setState((prev) => prev.baseThreadId === baseThreadId ? pendingState : prev);

    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    try {
      const res = await fetch(`${API_BASE_URL}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ message: input, thread_id: baseThreadId, parent_message_id: parentMessageId ?? undefined }),
        credentials: "include",
        signal: ac.signal,
      });

      if (!res.ok || !res.body) {
        if (res.status === 401) { notifyUnauthorized(); throw new Error("登录状态已失效，请重新登录"); }
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
      let latestAgentSteps: AgentStep[] = [];
      let realUserMsgId: number | null = null;
      let streamCompleted = false;

      while (!streamCompleted) {
        if (!mountedRef.current || ac.signal.aborted) break;
        const { done, value } = await reader.read();
        if (done || !mountedRef.current || ac.signal.aborted) break;

        const parsed = parseStreamEvents(
          { buffer, eventType },
          decoder.decode(value, { stream: true })
        );
        buffer = parsed.buffer;
        eventType = parsed.eventType;

        for (const { eventType: currentEventType, data } of parsed.events) {

          if (currentEventType === "error") {
            throw new Error(typeof data.message === "string" ? data.message : "流式响应失败");
          }

          try {
            if (typeof data.agent_name === "string") {
              agentName = data.agent_name;
              updateThreadState(baseThreadId, { streamingAgent: agentName });
              setActiveAgent(agentName);
            }
            if (typeof data.text === "string") {
              fullText += data.text;
              updateThreadState(baseThreadId, { streamingText: fullText });
            }
            if (typeof data.final_answer === "string" && data.final_answer) {
              fullText = data.final_answer;
              updateThreadState(baseThreadId, { streamingText: fullText });
            }
            if (Array.isArray(data.sources)) {
              latestSources = data.sources.filter((source): source is string => typeof source === "string");
            }
            if (Array.isArray(data.agent_steps)) {
              latestAgentSteps = toAgentSteps(data.agent_steps);
            }
            if (typeof data.tool_name === "string") {
              const isStart = data.status === "start";
              updateThreadState(baseThreadId, { activeTool: isStart ? data.tool_name : null });
              setActiveTool(isStart ? data.tool_name : null);
            }
            if (data.confidence !== undefined) {
              latestGovernance = toGovernance(data);
              updateThreadState(baseThreadId, { streamingGovernance: latestGovernance });
            }
            if (typeof data.label === "string" && currentEventType === "status") {
              updateThreadState(baseThreadId, { statusLabel: data.label });
              setStatusLabel(data.label);
            }
            if (currentEventType === "done") {
              // Backfill real user message id from backend
              if (typeof data.user_msg_id === "number") {
                realUserMsgId = data.user_msg_id;
              }
              streamCompleted = true;
            }
          } catch { /* skip malformed SSE data */ }
          if (streamCompleted) break;
        }
      }

      if (!mountedRef.current) return;

      const assistantMsg: Message = {
        id: nextLocalMessageId(),
        role: "assistant", content: fullText || "（未收到回复内容）", agentName,
        sources: latestSources, agentSteps: latestAgentSteps,
        governance: latestGovernance ?? undefined,
        parentId: realUserMsgId ?? tempId, siblingsOrder: 0, childCount: 0,
        timestamp: new Date(),
      };
      const cached = streamStateByThreadRef.current.get(baseThreadId) ?? stateRef.current;
      // Replace temp user msg id with real id if available
      const fixedMessages = realUserMsgId != null
        ? cached.messages.map((m) => m.id === tempId ? { ...m, id: realUserMsgId } : m)
        : cached.messages;
      const fixedCached = { ...cached, messages: fixedMessages };
      const completedState = finalizeThreadState(fixedCached, assistantMsg);
      streamStateByThreadRef.current.set(baseThreadId, completedState);
      setStreaming(false);
      triggerTrackingRefresh();
      evictCache();
      stateRef.current = stateRef.current.baseThreadId === baseThreadId ? completedState : stateRef.current;
      setState((prev) => prev.baseThreadId === baseThreadId ? completedState : prev);
    } catch (error: unknown) {
      if (!mountedRef.current) return;
      if (error instanceof DOMException && error.name === "AbortError") return;
      const msg = getErrorMessage(error, "聊天请求失败");
      const errorMsg: Message = { id: nextLocalMessageId(), role: "assistant", content: `系统错误: ${msg}`, agentName: "system", parentId: tempId, siblingsOrder: 0, childCount: 0, timestamp: new Date() };
      const cached = streamStateByThreadRef.current.get(baseThreadId) ?? stateRef.current;
      const failedState = finalizeThreadState(cached, errorMsg);
      streamStateByThreadRef.current.set(baseThreadId, failedState);
      setStreaming(false);
      evictCache();
      stateRef.current = stateRef.current.baseThreadId === baseThreadId ? failedState : stateRef.current;
      setState((prev) => prev.baseThreadId === baseThreadId ? failedState : prev);
    }
  }, [setState, authenticated, updateThreadState, evictCache, nextLocalMessageId, setActiveAgent, setStatusLabel, setActiveTool, setStreaming, triggerTrackingRefresh]);

  const loadConversation = useCallback(async (conversationId: number) => {
    if (!authenticated) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/chat/conversations/${conversationId}`, { headers: { ...getAuthHeaders() }, credentials: "include" });
      if (!res.ok) { if (res.status === 401) notifyUnauthorized(); return; }
      const detail: ConversationDetail = await res.json();
      // Map API snake_case fields → frontend camelCase
      const msgs: Message[] = (detail.messages || []).map((m) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        agentName: m.agent_name ?? undefined,
        sources: m.sources || [],
        governance: m.governance && typeof m.governance === "object"
          ? toGovernance(m.governance as Record<string, unknown>)
          : undefined,
        parentId: m.parent_id,
        siblingsOrder: m.siblings_order,
        childCount: m.child_count,
        timestamp: new Date(m.created_at),
      }));
      // Set activeLeafId to the last message id (default branch)
      const lastMsg = msgs.length > 0 ? msgs[msgs.length - 1] : null;
      const baseThread = getBaseThreadId(detail.thread_id);
      const cachedStreamingState = streamStateByThreadRef.current.get(baseThread)
        ?? streamStateByThreadRef.current.get(detail.thread_id)
        ?? Array.from(streamStateByThreadRef.current.values()).find((cached) => (
          cached.loading && (cached.conversationId === detail.id || getBaseThreadId(cached.baseThreadId) === baseThread)
        ));
      if (cachedStreamingState?.loading) {
        const restoredState = { ...cachedStreamingState, baseThreadId: baseThread, conversationId: detail.id };
        stateRef.current = restoredState;
        setState(restoredState);
        return;
      }
      if (cachedStreamingState && cachedStreamingState.messages.length > msgs.length) {
        const mergedState: ChatPanelState = {
          ...cachedStreamingState,
          loading: false, streamingText: "", streamingAgent: "",
          activeTool: null, streamingGovernance: null, statusLabel: "",
          baseThreadId: baseThread, conversationId: detail.id,
        };
        stateRef.current = mergedState;
        setState(mergedState);
        return;
      }
      const loadedState: ChatPanelState = {
        messages: msgs, input: "", loading: false,
        streamingText: "", streamingAgent: "",
        activeTool: null, streamingGovernance: null, statusLabel: "",
        baseThreadId: baseThread, conversationId: detail.id,
        activeLeafId: lastMsg?.id ?? null,
      };
      stateRef.current = loadedState;
      setState(loadedState);
    } catch { /* Load conversation failed — non-critical */ }
  }, [setState, authenticated]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    const cur = stateRef.current;
    if (cur.loading) {
      const partialText = cur.streamingText;
      const parentId = getLastUserMessageId(cur.messages);
      const partialMsg: Message | undefined = partialText
        ? { id: nextLocalMessageId(), role: "assistant", content: partialText, agentName: cur.streamingAgent || undefined, parentId, siblingsOrder: 0, childCount: 0, timestamp: new Date() }
        : undefined;
      const nextMessages = partialMsg ? [...cur.messages, partialMsg] : cur.messages;
      const stoppedState: ChatPanelState = {
        ...cur, messages: nextMessages, ...CLEARED_STREAM,
      };
      stateRef.current = stoppedState;
      setState(stoppedState);
      resetActivity();
      setStreaming(false);
    }
  }, [nextLocalMessageId, setState, resetActivity, setStreaming]);

  const regenerate = useCallback(() => {
    const cur = stateRef.current;
    if (cur.loading) return;
    const lastUserIdx = cur.messages.findLastIndex((m) => m.role === "user");
    if (lastUserIdx === -1) return;
    const lastUserMsg = cur.messages[lastUserIdx];
    // Branch from the parent of the last user message (same parent = sibling = branch)
    const branchParentId = lastUserMsg.parentId ?? null;
    // Remove last user message and all messages after it (assistant reply)
    const trimmedMessages = cur.messages.slice(0, lastUserIdx);
    // Reset activeLeafId to last remaining message or null
    const newLeafId = trimmedMessages.length > 0
      ? trimmedMessages[trimmedMessages.length - 1].id ?? null
      : null;
    const regeneratedState: ChatPanelState = {
      ...cur, messages: trimmedMessages, input: lastUserMsg.content,
      activeLeafId: newLeafId,
    };
    stateRef.current = regeneratedState;
    setState(regeneratedState);
    // sendMessage with branchParentId creates a new branch
    void sendMessage(branchParentId);
  }, [setState, sendMessage]);

  const newChat = useCallback(() => {
    const nextState: ChatPanelState = {
      messages: [], input: "", loading: false,
      streamingText: "", streamingAgent: "",
      activeTool: null, streamingGovernance: null, statusLabel: "",
      baseThreadId: generateThreadId(), conversationId: null,
      activeLeafId: null,
    };
    stateRef.current = nextState;
    setState(nextState);
  }, [setState]);

  return { state, sendMessage, stop, regenerate, updateState, loadConversation, newChat };
}
