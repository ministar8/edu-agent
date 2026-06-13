"use client";

import { memo, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { useAgentActivity } from "@/shared/contexts/AgentActivityContext";

// ── Agent metadata ──────────────────────────────────────────

const AGENT_META: Record<string, { label: string; sub: string; bg: string; text: string; border: string; icon: string }> = {
  supervisor: {
    label: "Supervisor 调度Agent",
    sub: "分析问题 → 路由分发",
    bg: "#f0fdf4",
    text: "#166534",
    border: "#bbf7d0",
    icon: "🎯",
  },
  knowledge_agent: {
    label: "知识点检索Agent",
    sub: "RAG检索教材",
    bg: "#eff6ff",
    text: "#1e40af",
    border: "#bfdbfe",
    icon: "📚",
  },
  question_agent: {
    label: "题目生成Agent",
    sub: "检索题库→生成新题",
    bg: "#fff1f2",
    text: "#9f1239",
    border: "#fecdd3",
    icon: "✏️",
  },
  grading_agent: {
    label: "批改评估Agent",
    sub: "检索标准答案→评分",
    bg: "#f5f3ff",
    text: "#5b21b6",
    border: "#ddd6fe",
    icon: "📝",
  },
  path_agent: {
    label: "学习路径推荐Agent",
    sub: "检索知识图谱→推荐",
    bg: "#fdf2f8",
    text: "#9d174d",
    border: "#fbcfe8",
    icon: "🗺️",
  },
  rag_layer: {
    label: "RAG 检索增强层",
    sub: "向量数据库 + 语义检索 + 重排序",
    bg: "#f0fdfa",
    text: "#115e59",
    border: "#99f6e4",
    icon: "🔍",
  },
};

const EDGE_META: Record<string, { label: string; color: string }> = {
  "e-supervisor-knowledge": { label: "知识点查询", color: "#43e97b" },
  "e-supervisor-question": { label: "出题请求", color: "#fa709a" },
  "e-supervisor-grading": { label: "批改请求", color: "#a18cd1" },
  "e-supervisor-path": { label: "学习建议", color: "#fccb90" },
  "e-knowledge-rag": { label: "", color: "#38b2ac" },
  "e-question-rag": { label: "", color: "#ed64a6" },
  "e-grading-rag": { label: "", color: "#9f7aea" },
  "e-path-rag": { label: "", color: "#d53f8c" },
};

const AGENT_TO_EDGE: Record<string, string> = {
  knowledge_agent: "e-supervisor-knowledge",
  question_agent: "e-supervisor-question",
  grading_agent: "e-supervisor-grading",
  path_agent: "e-supervisor-path",
};

const AGENT_TO_RAG_EDGE: Record<string, string> = {
  knowledge_agent: "e-knowledge-rag",
  question_agent: "e-question-rag",
  grading_agent: "e-grading-rag",
  path_agent: "e-path-rag",
};

// ── Build nodes with activity-aware styling ───────────────────

function buildNodes(activeAgent: string, isStreaming: boolean): Node[] {
  // Layout: supervisor top-center, 4 agents middle row, RAG bottom-center
  // ReactFlow position = top-left corner, so subtract width/2 to center
  const agentW = 190;
  const agentGap = 40;
  const startX = 50; // leftmost agent left edge
  const agentCenters = [0, 1, 2, 3].map(i => startX + i * (agentW + agentGap) + agentW / 2);
  const midX = (agentCenters[0] + agentCenters[3]) / 2; // center of agent row

  const supervisorW = 260;
  const ragW = 400;

  const positions: Record<string, { x: number; y: number }> = {
    supervisor: { x: midX - supervisorW / 2, y: 20 },
    knowledge_agent: { x: startX + 0 * (agentW + agentGap), y: 240 },
    question_agent: { x: startX + 1 * (agentW + agentGap), y: 240 },
    grading_agent: { x: startX + 2 * (agentW + agentGap), y: 240 },
    path_agent: { x: startX + 3 * (agentW + agentGap), y: 240 },
    rag_layer: { x: midX - ragW / 2, y: 500 },
  };

  const widths: Record<string, number> = {
    supervisor: supervisorW,
    knowledge_agent: agentW,
    question_agent: agentW,
    grading_agent: agentW,
    path_agent: agentW,
    rag_layer: ragW,
  };

  return Object.entries(AGENT_META).map(([id, meta]) => {
    const isActive = activeAgent === id;
    const isRagActive = id === "rag_layer" && isStreaming && AGENT_TO_RAG_EDGE[activeAgent];
    const isDimmed = isStreaming && !isActive && !isRagActive && id !== "supervisor" && !(activeAgent === "supervisor" && id === "rag_layer");
    const isSupervisorActive = activeAgent === "supervisor" && id === "supervisor";

    const scale = isActive || isSupervisorActive ? 1.05 : isRagActive ? 1.02 : 1;
    const opacity = isDimmed ? 0.35 : 1;
    const glow = isActive || isSupervisorActive
      ? "0 0 20px rgba(5,150,105,0.5), 0 0 40px rgba(5,150,105,0.2)"
      : isRagActive
        ? "0 0 12px rgba(11,163,96,0.3)"
        : "0 4px 12px rgba(0,0,0,0.05)";
    const borderExtra = isActive || isSupervisorActive ? "3px solid #fbbf24" : `2px solid ${meta.border}`;

    return {
      id,
      type: "default",
      position: positions[id],
      data: {
        label: (
          <div
            className="text-center rounded-xl select-none"
            style={{
              background: meta.bg,
              color: meta.text,
              border: borderExtra,
              padding: id === "supervisor" ? "12px 24px" : id === "rag_layer" ? "12px 32px" : "10px 20px",
              boxShadow: glow,
              transform: `scale(${scale})`,
              transformOrigin: "center center",
              transition: "all 300ms cubic-bezier(0.4, 0, 0.2, 1)",
              opacity,
            }}
          >
            <div className="font-bold text-base leading-tight">
              {meta.icon} {meta.label}
            </div>
            <div className="text-xs opacity-80 mt-0.5">{meta.sub}</div>
            {isActive && (
              <div className="mt-1 flex items-center justify-center gap-1">
                <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-yellow-300" />
                <span className="text-[10px] opacity-90 font-medium">运行中</span>
              </div>
            )}
          </div>
        ),
      },
      style: {
        width: widths[id],
        padding: 0,
        background: "transparent",
        border: "none",
        boxShadow: "none",
      },
    };
  });
}

function buildEdges(activeAgent: string, isStreaming: boolean, activeTool: string | null): Edge[] {
  const edgeDefs: Array<{ id: string; source: string; target: string; dashed?: boolean }> = [
    { id: "e-supervisor-knowledge", source: "supervisor", target: "knowledge_agent" },
    { id: "e-supervisor-question", source: "supervisor", target: "question_agent" },
    { id: "e-supervisor-grading", source: "supervisor", target: "grading_agent" },
    { id: "e-supervisor-path", source: "supervisor", target: "path_agent" },
    { id: "e-knowledge-rag", source: "knowledge_agent", target: "rag_layer", dashed: true },
    { id: "e-question-rag", source: "question_agent", target: "rag_layer", dashed: true },
    { id: "e-grading-rag", source: "grading_agent", target: "rag_layer", dashed: true },
    { id: "e-path-rag", source: "path_agent", target: "rag_layer", dashed: true },
  ];

  const activeEdgeFromSupervisor = AGENT_TO_EDGE[activeAgent] || "";
  const activeEdgeToRag = (isStreaming && activeTool) ? (AGENT_TO_RAG_EDGE[activeAgent] || "") : "";

  return edgeDefs.map(({ id, source, target, dashed }) => {
    const meta = EDGE_META[id];
    const isActive = id === activeEdgeFromSupervisor || id === activeEdgeToRag;
    const isDimmed = isStreaming && !isActive && source === "supervisor" && activeAgent !== "supervisor";

    return {
      id,
      source,
      target,
      label: meta.label || undefined,
      animated: isActive,
      style: {
        stroke: meta.color,
        strokeWidth: isActive ? 3 : 1.5,
        opacity: isDimmed ? 0.2 : 1,
        strokeDasharray: dashed ? "5 5" : undefined,
        transition: "all 0.4s ease",
      },
      markerEnd: { type: MarkerType.ArrowClosed, color: meta.color },
    };
  });
}

// ── Activity log panel ────────────────────────────────────────

function ActivityLog() {
  const { activity } = useAgentActivity();

  if (activity.history.length === 0 && !activity.isStreaming) return null;

  const recentHistory = activity.history.slice(-6);

  return (
    <div className="absolute bottom-4 left-4 z-10 w-72 rounded-xl border border-slate-200 bg-white/95 backdrop-blur-sm shadow-lg">
      <div className="border-b border-slate-100 px-3 py-2">
        <h3 className="text-xs font-semibold text-slate-600">Agent 执行日志</h3>
      </div>
      <div className="max-h-40 overflow-y-auto px-3 py-2 space-y-1">
        {recentHistory.map((entry, i) => {
          const meta = AGENT_META[entry.agent];
          const isStart = entry.type === "start";
          const isComplete = entry.type === "complete";
          const isToolStart = entry.type === "tool_start";
          const isToolEnd = entry.type === "tool_end";
          return (
            <div key={i} className="flex items-center gap-1.5 text-[11px]">
              <span className={
                isComplete ? "text-emerald-500" :
                isStart ? "text-amber-500" :
                isToolStart ? "text-blue-500" :
                isToolEnd ? "text-slate-400" :
                "text-slate-400"
              }>
                {isComplete ? "✓" : isStart ? "▶" : isToolStart ? "⚙" : "⚙"}
              </span>
              <span className="font-medium text-slate-700">{meta?.icon} {meta?.label?.split(" ")[0] || entry.agent}</span>
              {entry.tool && <span className="text-slate-400">.{entry.tool}</span>}
              <span className="ml-auto text-slate-300">
                {new Date(entry.timestamp).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
              </span>
            </div>
          );
        })}
        {activity.isStreaming && activity.statusLabel && (
          <div className="flex items-center gap-1.5 text-[11px] text-amber-600 font-medium">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-amber-400" />
            {activity.statusLabel}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────

function AgentFlowInner() {
  const { activity } = useAgentActivity();
  const nodes = useMemo(
    () => buildNodes(activity.activeAgent, activity.isStreaming),
    [activity.activeAgent, activity.isStreaming],
  );
  const edges = useMemo(
    () => buildEdges(activity.activeAgent, activity.isStreaming, activity.activeTool),
    [activity.activeAgent, activity.isStreaming, activity.activeTool],
  );

  return (
    <div className="w-full h-full flex flex-col relative">
      <div className="shrink-0 p-4 bg-white border-b">
        <h2 className="text-lg font-bold text-slate-800">多Agent协作流程图</h2>
        <p className="text-sm text-slate-500">
          Supervisor调度 → 子Agent处理 → RAG检索增强
          {activity.isStreaming && (
            <span className="ml-2 inline-flex items-center gap-1 text-amber-600 font-medium">
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-amber-400" />
              实时协作中
            </span>
          )}
        </p>
      </div>
      <div className="h-[420px] w-full shrink-0">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          fitView
          fitViewOptions={{ padding: 0.3, minZoom: 0.5, maxZoom: 1.2 }}
          attributionPosition="bottom-left"
          proOptions={{ hideAttribution: true }}
          minZoom={0.3}
          maxZoom={2}
        >
          <Background color="#e2e8f0" gap={20} />
          <Controls />
          <MiniMap
            nodeStrokeColor="#059669"
            nodeColor="#059669"
            maskColor="rgba(5, 150, 105, 0.1)"
          />
        </ReactFlow>
      </div>
      <ActivityLog />
    </div>
  );
}

export default memo(AgentFlowInner);
