"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

export interface AgentActivity {
  /** 当前活跃的 Agent 名称 (supervisor / knowledge_agent / question_agent / grading_agent / path_agent) */
  activeAgent: string;
  /** 当前阶段标签 (正在检索知识库... / 正在生成题目... 等) */
  statusLabel: string;
  /** 当前正在执行的工具名 */
  activeTool: string | null;
  /** 是否正在流式处理 */
  isStreaming: boolean;
  /** 最近一次完成的 Agent 名称 */
  lastCompletedAgent: string;
  /** Agent 执行历史记录 */
  history: AgentHistoryEntry[];
}

export interface AgentHistoryEntry {
  agent: string;
  tool?: string;
  label: string;
  timestamp: number;
  type: "start" | "tool_start" | "tool_end" | "complete";
}

const DEFAULT_ACTIVITY: AgentActivity = {
  activeAgent: "",
  statusLabel: "",
  activeTool: null,
  isStreaming: false,
  lastCompletedAgent: "",
  history: [],
};

type AgentActivityContextValue = {
  activity: AgentActivity;
  setActiveAgent: (agent: string) => void;
  setStatusLabel: (label: string) => void;
  setActiveTool: (tool: string | null) => void;
  setStreaming: (streaming: boolean) => void;
  reset: () => void;
};

const AgentActivityContext = createContext<AgentActivityContextValue | null>(null);

export function AgentActivityProvider({ children }: { children: ReactNode }) {
  const [activity, setActivity] = useState<AgentActivity>(DEFAULT_ACTIVITY);

  const setActiveAgent = useCallback((agent: string) => {
    setActivity((prev) => ({
      ...prev,
      activeAgent: agent,
      isStreaming: true,
      history: [
        ...prev.history.slice(-19),
        { agent, label: prev.statusLabel || agent, timestamp: Date.now(), type: "start" },
      ],
    }));
  }, []);

  const setStatusLabel = useCallback((label: string) => {
    setActivity((prev) => ({ ...prev, statusLabel: label }));
  }, []);

  const setActiveTool = useCallback((tool: string | null) => {
    setActivity((prev) => ({
      ...prev,
      activeTool: tool,
      history: tool
        ? [
            ...prev.history.slice(-19),
            { agent: prev.activeAgent, tool, label: `${tool}`, timestamp: Date.now(), type: "tool_start" },
          ]
        : prev.activeTool
          ? [
              ...prev.history.slice(-19),
              { agent: prev.activeAgent, tool: prev.activeTool, label: `${prev.activeTool}`, timestamp: Date.now(), type: "tool_end" },
            ]
          : prev.history,
    }));
  }, []);

  const setStreaming = useCallback((streaming: boolean) => {
    setActivity((prev) => {
      if (!streaming && prev.activeAgent) {
        return {
          ...prev,
          isStreaming: false,
          lastCompletedAgent: prev.activeAgent,
          activeAgent: "",
          statusLabel: "",
          activeTool: null,
          history: [
            ...prev.history.slice(-19),
            { agent: prev.activeAgent, label: prev.statusLabel || prev.activeAgent, timestamp: Date.now(), type: "complete" },
          ],
        };
      }
      return { ...prev, isStreaming: streaming };
    });
  }, []);

  const reset = useCallback(() => {
    setActivity(DEFAULT_ACTIVITY);
  }, []);

  return (
    <AgentActivityContext.Provider value={{ activity, setActiveAgent, setStatusLabel, setActiveTool, setStreaming, reset }}>
      {children}
    </AgentActivityContext.Provider>
  );
}

export function useAgentActivity() {
  const ctx = useContext(AgentActivityContext);
  if (!ctx) throw new Error("useAgentActivity must be used within AgentActivityProvider");
  return ctx;
}
