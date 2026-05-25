"use client";

import { useEffect, useState } from "react";
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

import { http } from "@/lib/http";

export default function AgentFlow() {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);

  useEffect(() => {
    http.get("/api/visualization/agent-graph")
      .then((res) => {
        const data = res.data as { nodes: Node[]; edges: Edge[] };
        setNodes(data.nodes);
        setEdges(data.edges);
      })
      .catch(() => {
        setNodes(defaultNodes);
        setEdges(defaultEdges);
      });
  }, []);

  const displayNodes = nodes.length > 0 ? nodes : defaultNodes;
  const displayEdges = edges.length > 0 ? edges : defaultEdges;

  return (
    <div className="w-full h-full">
      <div className="p-4 bg-white border-b">
        <h2 className="text-lg font-bold text-slate-800">多Agent协作流程图</h2>
        <p className="text-sm text-slate-500">
          Supervisor调度 → 子Agent处理 → RAG检索增强，实时展示Agent间协作关系
        </p>
      </div>
      <div className="w-full" style={{ height: "calc(100vh - 200px)" }}>
        <ReactFlow
          nodes={displayNodes}
          edges={displayEdges}
          fitView
          attributionPosition="bottom-left"
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
    </div>
  );
}

const defaultNodes: Node[] = [
  {
    id: "supervisor",
    type: "default",
    position: { x: 400, y: 50 },
    data: {
      label: (
        <div className="text-center">
          <div className="font-bold text-lg">Supervisor 调度Agent</div>
          <div className="text-xs opacity-80">分析问题 → 路由分发</div>
        </div>
      ),
    },
    style: {
      background: "linear-gradient(135deg, #059669 0%, #10b981 100%)",
      color: "white",
      border: "2px solid #047857",
      borderRadius: "12px",
      padding: "12px 24px",
      width: 220,
    },
  },
  {
    id: "knowledge_agent",
    type: "default",
    position: { x: 50, y: 280 },
    data: {
      label: (
        <div className="text-center">
          <div className="font-bold">知识点检索Agent</div>
          <div className="text-xs opacity-70">RAG检索教材</div>
        </div>
      ),
    },
    style: {
      background: "linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)",
      color: "#1a202c",
      border: "2px solid #38b2ac",
      borderRadius: "12px",
      padding: "10px 20px",
      width: 180,
    },
  },
  {
    id: "question_agent",
    type: "default",
    position: { x: 280, y: 280 },
    data: {
      label: (
        <div className="text-center">
          <div className="font-bold">题目生成Agent</div>
          <div className="text-xs opacity-70">检索题库→生成新题</div>
        </div>
      ),
    },
    style: {
      background: "linear-gradient(135deg, #fa709a 0%, #fee140 100%)",
      color: "#1a202c",
      border: "2px solid #ed64a6",
      borderRadius: "12px",
      padding: "10px 20px",
      width: 180,
    },
  },
  {
    id: "grading_agent",
    type: "default",
    position: { x: 510, y: 280 },
    data: {
      label: (
        <div className="text-center">
          <div className="font-bold">批改评估Agent</div>
          <div className="text-xs opacity-70">检索标准答案→评分</div>
        </div>
      ),
    },
    style: {
      background: "linear-gradient(135deg, #a18cd1 0%, #fbc2eb 100%)",
      color: "#1a202c",
      border: "2px solid #9f7aea",
      borderRadius: "12px",
      padding: "10px 20px",
      width: 180,
    },
  },
  {
    id: "path_agent",
    type: "default",
    position: { x: 740, y: 280 },
    data: {
      label: (
        <div className="text-center">
          <div className="font-bold">学习路径推荐Agent</div>
          <div className="text-xs opacity-70">检索知识图谱→推荐</div>
        </div>
      ),
    },
    style: {
      background: "linear-gradient(135deg, #fccb90 0%, #d57eeb 100%)",
      color: "#1a202c",
      border: "2px solid #d53f8c",
      borderRadius: "12px",
      padding: "10px 20px",
      width: 180,
    },
  },
  {
    id: "rag_layer",
    type: "default",
    position: { x: 200, y: 500 },
    data: {
      label: (
        <div className="text-center">
          <div className="font-bold text-lg">RAG 检索增强层</div>
          <div className="text-xs opacity-80">向量数据库 + 语义检索 + 重排序</div>
        </div>
      ),
    },
    style: {
      background: "linear-gradient(135deg, #0ba360 0%, #3cba92 100%)",
      color: "white",
      border: "2px solid #38a169",
      borderRadius: "12px",
      padding: "12px 32px",
      width: 400,
    },
  },
];

const defaultEdges: Edge[] = [
  {
    id: "e-supervisor-knowledge",
    source: "supervisor",
    target: "knowledge_agent",
    label: "知识点查询",
    animated: true,
    style: { stroke: "#43e97b", strokeWidth: 2 },
    markerEnd: { type: MarkerType.ArrowClosed, color: "#43e97b" },
  },
  {
    id: "e-supervisor-question",
    source: "supervisor",
    target: "question_agent",
    label: "出题请求",
    animated: true,
    style: { stroke: "#fa709a", strokeWidth: 2 },
    markerEnd: { type: MarkerType.ArrowClosed, color: "#fa709a" },
  },
  {
    id: "e-supervisor-grading",
    source: "supervisor",
    target: "grading_agent",
    label: "批改请求",
    animated: true,
    style: { stroke: "#a18cd1", strokeWidth: 2 },
    markerEnd: { type: MarkerType.ArrowClosed, color: "#a18cd1" },
  },
  {
    id: "e-supervisor-path",
    source: "supervisor",
    target: "path_agent",
    label: "学习建议",
    animated: true,
    style: { stroke: "#fccb90", strokeWidth: 2 },
    markerEnd: { type: MarkerType.ArrowClosed, color: "#fccb90" },
  },
  {
    id: "e-knowledge-rag",
    source: "knowledge_agent",
    target: "rag_layer",
    style: { stroke: "#38b2ac", strokeWidth: 1.5, strokeDasharray: "5 5" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "#38b2ac" },
  },
  {
    id: "e-question-rag",
    source: "question_agent",
    target: "rag_layer",
    style: { stroke: "#ed64a6", strokeWidth: 1.5, strokeDasharray: "5 5" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "#ed64a6" },
  },
  {
    id: "e-grading-rag",
    source: "grading_agent",
    target: "rag_layer",
    style: { stroke: "#9f7aea", strokeWidth: 1.5, strokeDasharray: "5 5" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "#9f7aea" },
  },
  {
    id: "e-path-rag",
    source: "path_agent",
    target: "rag_layer",
    style: { stroke: "#d53f8c", strokeWidth: 1.5, strokeDasharray: "5 5" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "#d53f8c" },
  },
];
