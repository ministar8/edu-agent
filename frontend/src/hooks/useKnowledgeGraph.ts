import { useCallback, useEffect, useState } from "react";
import { Edge, MarkerType, Node } from "@xyflow/react";

import { getErrorMessage } from "@/lib/errors";
import { http } from "@/lib/http";
import type { KnowledgeGraphEdge, KnowledgeGraphNode } from "@/types/knowledgeGraph";
import { demoGraphEdges, demoGraphNodes } from "@/components/knowledge-graph/demoGraphData";

const relationColors: Record<string, string> = {
  PREREQUISITE_OF: "#f59e0b",
  RELATED_TO: "#10b981",
};

function toReactNodes(graphNodes: KnowledgeGraphNode[]): Node[] {
  return graphNodes.map((node, index) => {
    const angle = (2 * Math.PI * index) / graphNodes.length;
    const radius = 250;
    return {
      id: node.id,
      type: "default",
      position: {
        x: 400 + radius * Math.cos(angle),
        y: 300 + radius * Math.sin(angle),
      },
      data: { label: node.id },
      style: {
        background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
        color: "white",
        border: "2px solid #5a67d8",
        borderRadius: "8px",
        padding: "8px 16px",
        fontSize: "13px",
      },
    };
  });
}

function toReactEdges(graphEdges: KnowledgeGraphEdge[]): Edge[] {
  return graphEdges.map((edge) => ({
    id: `${edge.source}-${edge.target}`,
    source: edge.source,
    target: edge.target,
    label: edge.relation === "PREREQUISITE_OF" ? "前置" : "相关",
    animated: edge.relation === "PREREQUISITE_OF",
    style: {
      stroke: relationColors[edge.relation] || "#94a3b8",
      strokeWidth: 2,
    },
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: relationColors[edge.relation] || "#94a3b8",
    },
  }));
}

export function useKnowledgeGraph() {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [showImport, setShowImport] = useState(false);
  const [error, setError] = useState("");

  const fetchGraph = useCallback(async () => {
    try {
      const res = await http.get("/api/visualization/knowledge-graph");
      setNodes(toReactNodes(res.data.nodes));
      setEdges(toReactEdges(res.data.edges));
      setError("");
    } catch (error: unknown) {
      setNodes([]);
      setEdges([]);
      setError(getErrorMessage(error, "知识图谱加载失败"));
    }
  }, []);

  useEffect(() => {
    void fetchGraph();
  }, [fetchGraph]);

  const importDemoData = useCallback(async () => {
    try {
      await http.post("/api/visualization/knowledge-graph/import", {
        nodes: demoGraphNodes,
        edges: demoGraphEdges,
      });
      void fetchGraph();
      setShowImport(false);
    } catch (error: unknown) {
      setError(getErrorMessage(error, "导入失败"));
    }
  }, [fetchGraph]);

  return {
    nodes,
    edges,
    showImport,
    error,
    setShowImport,
    fetchGraph,
    importDemoData,
  };
}
