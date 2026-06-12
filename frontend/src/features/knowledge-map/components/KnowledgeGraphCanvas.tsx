import { memo, useMemo } from "react";
import { Background, Controls, Edge, Handle, MiniMap, Node, NodeChange, NodeProps, Position, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { KnowledgeGraphEmptyState } from "./KnowledgeGraphEmptyState";
import type { KnowledgeMapNodeData } from "@/shared/types/knowledgeGraph";

type KnowledgeGraphCanvasProps = {
  nodes: Node<KnowledgeMapNodeData>[];
  edges: Edge[];
  error: string;
  selectedNodeId?: string;
  onSelectNode: (node: Node<KnowledgeMapNodeData> | null) => void;
  onNodesChange: (changes: NodeChange<Node<KnowledgeMapNodeData>>[]) => void;
};

function circleSize(kind: KnowledgeMapNodeData["kind"]) {
  if (kind === "root") return 100;
  return 72;
}

function KnowledgeCircleNode({ data }: NodeProps<Node<KnowledgeMapNodeData>>) {
  const size = circleSize(data.kind);
  const dimmed = data.highlight === "dimmed";
  const selected = data.highlight === "selected";
  const related = data.highlight === "related";
  const isRoot = data.kind === "root";
  const isLevel1 = data.kind === "level1";

  // Text color: modern soft deep colors
  const textColor = isRoot ? "#9f1239" : isLevel1 ? "#3730a3" : "#ffffff";
  const borderColor = selected
    ? "#fbbf24"
    : isRoot
      ? "#fecdd3"
      : "#c7d2fe";

  return (
    <div
      className="group relative"
      style={{
        width: size,
        height: size,
        opacity: dimmed ? 0.18 : 1,
        transform: selected ? "scale(1.08)" : related ? "scale(1.03)" : "scale(1)",
        transition: "opacity 180ms ease, transform 180ms ease",
      }}
    >
      <Handle id="top-target" type="target" position={Position.Top} className="!h-1 !w-1 !border-0 !bg-transparent" />
      <Handle id="right-target" type="target" position={Position.Right} className="!h-1 !w-1 !border-0 !bg-transparent" />
      <Handle id="bottom-target" type="target" position={Position.Bottom} className="!h-1 !w-1 !border-0 !bg-transparent" />
      <Handle id="left-target" type="target" position={Position.Left} className="!h-1 !w-1 !border-0 !bg-transparent" />
      <Handle id="top-source" type="source" position={Position.Top} className="!h-1 !w-1 !border-0 !bg-transparent" />
      <Handle id="right-source" type="source" position={Position.Right} className="!h-1 !w-1 !border-0 !bg-transparent" />
      <Handle id="bottom-source" type="source" position={Position.Bottom} className="!h-1 !w-1 !border-0 !bg-transparent" />
      <Handle id="left-source" type="source" position={Position.Left} className="!h-1 !w-1 !border-0 !bg-transparent" />

      <div
        className="flex shrink-0 items-center justify-center rounded-full text-center"
        style={{
          width: size,
          height: size,
          background: data.accent,
          boxShadow: selected
            ? `0 0 0 5px #ffffff, 0 0 0 10px ${data.accent}60, 0 16px 32px ${data.accent}30`
            : related
              ? `0 0 0 3px #ffffff, 0 0 0 7px ${data.accent}40, 0 10px 24px ${data.accent}20`
              : `0 6px 18px ${data.accent}20`,
          border: `2px solid ${borderColor}`,
        }}
      >
        <div style={{ color: textColor }}>
          {isRoot && (
            <div className="text-[12px] font-bold leading-tight">{data.label}</div>
          )}
          {isLevel1 && (
            <div>
              <div className="text-xs font-bold leading-tight">{data.label}</div>
              {data.childCount != null && data.childCount > 0 && (
                <div className="text-[9px] opacity-70 mt-0.5">{data.childCount}个知识点</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function nodeCenter(node: Node<KnowledgeMapNodeData>) {
  const size = circleSize(node.data.kind);
  return {
    x: node.position.x + size / 2,
    y: node.position.y + size / 2,
  };
}

function handleSide(from: Node<KnowledgeMapNodeData>, to: Node<KnowledgeMapNodeData>) {
  const a = nodeCenter(from);
  const b = nodeCenter(to);
  const dx = b.x - a.x;
  const dy = b.y - a.y;

  if (Math.abs(dx) > Math.abs(dy)) {
    return dx > 0 ? "right" : "left";
  }
  return dy > 0 ? "bottom" : "top";
}

function oppositeSide(side: string) {
  if (side === "right") return "left";
  if (side === "left") return "right";
  if (side === "bottom") return "top";
  return "bottom";
}

function KnowledgeGraphCanvasComponent({ nodes, edges, error, selectedNodeId, onSelectNode, onNodesChange }: KnowledgeGraphCanvasProps) {
  const relatedIds = useMemo(() => {
    if (!selectedNodeId) return new Set<string>();
    const ids = new Set<string>([selectedNodeId]);
    edges.forEach((edge) => {
      if (edge.source === selectedNodeId) ids.add(edge.target);
      if (edge.target === selectedNodeId) ids.add(edge.source);
    });
    return ids;
  }, [edges, selectedNodeId]);

  const nodeTypes = useMemo(() => ({ knowledgeCircle: KnowledgeCircleNode }), []);
  const visibleNodes = useMemo(() => nodes.map((node) => {
    const highlight: KnowledgeMapNodeData["highlight"] = !selectedNodeId
      ? "normal"
      : node.id === selectedNodeId
        ? "selected"
        : relatedIds.has(node.id)
          ? "related"
          : "dimmed";
    return {
      ...node,
      data: { ...node.data, highlight },
    };
  }), [nodes, relatedIds, selectedNodeId]);

  const visibleEdges = useMemo(() => {
    const nodeById = new Map(nodes.map((node) => [node.id, node]));
    return edges.map((edge) => {
      const sourceNode = nodeById.get(edge.source);
      const targetNode = nodeById.get(edge.target);
      const sourceSide = sourceNode && targetNode ? handleSide(sourceNode, targetNode) : "bottom";
      const targetSide = oppositeSide(sourceSide);
      const active = !selectedNodeId || edge.source === selectedNodeId || edge.target === selectedNodeId;

      return {
        ...edge,
        type: "default",
        sourceHandle: `${sourceSide}-source`,
        targetHandle: `${targetSide}-target`,
        pathOptions: { curvature: edge.style?.strokeDasharray ? 0.58 : 0.36 },
        style: {
          ...edge.style,
          opacity: active ? (edge.style?.strokeDasharray ? 0.72 : 0.9) : 0.08,
          strokeWidth: active && selectedNodeId ? 2.5 : edge.style?.strokeWidth,
        },
        markerEnd: active ? edge.markerEnd : undefined,
      };
    });
  }, [edges, nodes, selectedNodeId]);

  return (
    <div className="min-h-0 flex-1">
      {nodes.length > 0 ? (
        <div className="relative h-full overflow-hidden bg-white">
          <ReactFlow
            nodes={visibleNodes}
            edges={visibleEdges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.16 }}
            minZoom={0.45}
            maxZoom={1.6}
            onNodesChange={onNodesChange}
            onNodeClick={(_, node) => onSelectNode(node as Node<KnowledgeMapNodeData>)}
            onPaneClick={() => onSelectNode(null)}
          >
            <Background color="#eef2f7" gap={24} />
            <Controls />
            <MiniMap
              nodeStrokeColor={(node) => String((node.data as KnowledgeMapNodeData)?.border || "#334155")}
              nodeColor={(node) => String((node.data as KnowledgeMapNodeData)?.accent || "#64748b")}
              maskColor="rgba(148, 163, 184, 0.12)"
            />
          </ReactFlow>
        </div>
      ) : (
        <KnowledgeGraphEmptyState error={error} />
      )}
    </div>
  );
}

export const KnowledgeGraphCanvas = memo(KnowledgeGraphCanvasComponent);
