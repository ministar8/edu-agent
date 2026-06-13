import { useCallback, useEffect, useRef, useState } from "react";
import { applyNodeChanges, Edge, MarkerType, Node, NodeChange } from "@xyflow/react";

import { getErrorMessage } from "@/shared/lib/errors";
import { http } from "@/shared/lib/http";
import type {
  KnowledgeGraphEdge,
  KnowledgeMapNodeData,
} from "@/shared/types/knowledgeGraph";

type LabelSide = KnowledgeMapNodeData["labelSide"];

// ── Theme per category ────────────────────────────────────────

type Theme = {
  label: string;
  icon: string;
  root: string;
  level1: string;
  level2: string;
};

const themes: Record<string, Theme> = {
  data_structure: {
    label: "数据结构",
    icon: "🌳",
    root: "#ffe4e6",
    level1: "#e0e7ff",
    level2: "#71c978",
  },
  computer_organization: {
    label: "计算机组成原理",
    icon: "🖥️",
    root: "#ffe4e6",
    level1: "#e0e7ff",
    level2: "#71c978",
  },
  operating_system: {
    label: "操作系统",
    icon: "⚙️",
    root: "#ffe4e6",
    level1: "#e0e7ff",
    level2: "#71c978",
  },
  computer_network: {
    label: "计算机网络",
    icon: "🌐",
    root: "#ffe4e6",
    level1: "#e0e7ff",
    level2: "#71c978",
  },
};

const fallbackTheme: Theme = {
  label: "其他知识",
  icon: "📖",
  root: "#ffe4e6",
  level1: "#e0e7ff",
  level2: "#71c978",
};

function getTheme(category: string): Theme {
  return themes[category] || fallbackTheme;
}

// ── Layout helpers ────────────────────────────────────────────

function toRadians(degrees: number) {
  return (degrees * Math.PI) / 180;
}

function getCircularPoint(center: { x: number; y: number }, radius: number, angle: number) {
  return {
    x: center.x + Math.cos(angle) * radius,
    y: center.y + Math.sin(angle) * radius,
  };
}

function getLabelSide(angle: number): LabelSide {
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  if (Math.abs(cos) > Math.abs(sin)) return cos >= 0 ? "right" : "left";
  return sin >= 0 ? "bottom" : "top";
}

// ── Node builder ──────────────────────────────────────────────

const relationStyles: Record<string, { color: string; dashed?: boolean }> = {
  CONTAINS: { color: "#e2e8f0" },               // Very subtle slate-200 for tree branches
  PREREQUISITE_OF: { color: "#818cf8" },        // Modern indigo-400 for learning paths
  RELATED_TO: { color: "#fda4af", dashed: true }, // Soft rose-300 dashed for cross-subject relationships
};

function makeMapNode(
  id: string,
  label: string,
  description: string,
  category: string,
  kind: KnowledgeMapNodeData["kind"],
  position: { x: number; y: number },
  labelSide: LabelSide,
  childCount?: number,
  icon?: string,
): Node<KnowledgeMapNodeData> {
  const theme = getTheme(category);
  const accent = kind === "root" ? theme.root : kind === "level1" ? theme.level1 : theme.level2;

  return {
    id,
    type: "knowledgeCircle",
    position,
    draggable: true,
    data: {
      label,
      category,
      categoryLabel: theme.label,
      description,
      kind,
      accent,
      border: accent,
      highlight: "normal",
      labelSide,
      childCount,
      icon: icon || (kind === "root" ? theme.icon : undefined),
    } satisfies KnowledgeMapNodeData,
  };
}

// ── Build real hierarchical graph from API data ──────────────

interface HierarchicalNode {
  id: string;
  name: string;
  category: string;
  kind: "root" | "level1" | "level2";
  description: string;
  child_count?: number;
}

interface HierarchicalEdge {
  source: string;
  target: string;
  relation: string;
  weight?: number;
}

// Root positions: 4 subjects in a wide diamond layout, well-separated
const ROOT_POSITIONS: Record<string, { x: number; y: number }> = {
  data_structure: { x: 300, y: 150 },
  computer_organization: { x: 1200, y: 150 },
  operating_system: { x: 300, y: 800 },
  computer_network: { x: 1200, y: 800 },
};

function buildHierarchicalMap(
  apiNodes: HierarchicalNode[],
  apiEdges: HierarchicalEdge[],
) {
  const nodes: Node<KnowledgeMapNodeData>[] = [];
  const edges: KnowledgeGraphEdge[] = [];

  // Group nodes by kind (ignore level2 even if API returns them)
  const roots = apiNodes.filter((n) => n.kind === "root");
  const level1s = apiNodes.filter((n) => n.kind === "level1");

  // Place root nodes
  for (const root of roots) {
    const pos = ROOT_POSITIONS[root.category] || { x: 600, y: 400 };
    const labelSide: LabelSide = pos.y < 400 ? "top" : "bottom";
    const theme = getTheme(root.category);
    nodes.push(makeMapNode(
      root.id,
      root.name,
      root.description,
      root.category,
      "root",
      pos,
      labelSide,
      undefined,
      theme.icon,
    ));
  }

  // Place level1 nodes around their root
  const rootMap = new Map(roots.map((r) => [r.id, r]));
  const childrenOf = new Map<string, HierarchicalNode[]>();
  for (const l1 of level1s) {
    const parentId = apiEdges.find((e) => e.target === l1.id && e.relation === "CONTAINS")?.source;
    if (parentId) {
      const arr = childrenOf.get(parentId) || [];
      arr.push(l1);
      childrenOf.set(parentId, arr);
    }
  }

  const rootIds = Array.from(childrenOf.keys());
  for (const rootId of rootIds) {
    const children = childrenOf.get(rootId)!;
    const root = rootMap.get(rootId);
    if (!root) continue;
    const center = ROOT_POSITIONS[root.category] || { x: 750, y: 450 };
    const n = children.length;

    // Full 360-degree circle around root, starting from top (-90°)
    const startAngle = -90;
    const radius = 210;

    children.forEach((l1: HierarchicalNode, i: number) => {
      const angle = n > 1
        ? toRadians(startAngle + (360 * i) / n)
        : toRadians(startAngle);
      const pos = getCircularPoint(center, radius, angle);
      const labelSide = getLabelSide(angle);

      nodes.push(makeMapNode(
        l1.id,
        l1.name,
        l1.description,
        l1.category,
        "level1",
        pos,
        labelSide,
        l1.child_count,
      ));
    });
  }

  // Convert API edges to graph edges (skip edges involving level2 nodes)
  const nodeIds = new Set(nodes.map((n) => n.id));
  for (const e of apiEdges) {
    if (nodeIds.has(e.source) && nodeIds.has(e.target)) {
      edges.push({ source: e.source, target: e.target, relation: e.relation });
    }
  }

  return { nodes, edges };
}

// ── Edge converter ─────────────────────────────────────────────

function toReactEdges(graphEdges: KnowledgeGraphEdge[]): Edge[] {
  const seen = new Set<string>();
  return graphEdges
    .filter((edge) => {
      const key = `${edge.source}->${edge.target}:${edge.relation}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .map((edge) => {
      const isContains = edge.relation === "CONTAINS";
      const isRelated = edge.relation === "RELATED_TO";
      const isPrereq = edge.relation === "PREREQUISITE_OF";
      const style = relationStyles[edge.relation] || relationStyles.CONTAINS;
      
      return {
        id: `${edge.source}-${edge.target}-${edge.relation}`,
        source: edge.source,
        target: edge.target,
        animated: isPrereq,
        style: {
          stroke: style.color,
          strokeWidth: isRelated ? 1.5 : isContains ? 1.2 : 2.5,
          strokeDasharray: style.dashed ? "6 6" : undefined,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: style.color,
          width: isContains ? 10 : 14,
          height: isContains ? 10 : 14,
        },
      };
    });
}

// ── Focus helpers ──────────────────────────────────────────────

function normalizeFocusText(text: string) {
  return text.toLowerCase().replace(/[\s/\\:：、，,。()（）-]/g, "");
}

const focusAliases: Record<string, string[]> = {
  "TCP/UDP": ["TCP", "UDP", "传输层", "TCP连接", "拥塞控制"],
  "进程同步": ["进程同步", "信号量", "管程机制", "死锁"],
  "死锁": ["死锁", "进程同步", "信号量"],
  "内存管理": ["内存管理", "虚拟内存", "页面置换"],
  "树与二叉树": ["树形结构", "二叉树遍历", "哈夫曼树"],
  "图结构": ["图形结构", "最短路径", "最小生成树"],
  "排序算法": ["排序与查找", "快速排序", "散列表"],
  "查找结构": ["排序与查找", "散列表"],
  "网络层": ["网络层", "路由选择", "子网划分"],
  "数据链路层": ["数据链路层", "滑动窗口", "CSMA/CD"],
  "存储系统": ["存储系统", "Cache映射", "存储层次"],
  "指令系统": ["指令系统", "寻址方式", "CPU结构"],
  "CPU结构": ["CPU结构", "流水线", "控制器"],
};

function findFocusedNode(nodes: Node<KnowledgeMapNodeData>[], focusLabel: string) {
  const candidates = [focusLabel, ...(focusAliases[focusLabel] || [])]
    .map(normalizeFocusText)
    .filter(Boolean);

  return nodes.find((node) => {
    const label = normalizeFocusText(node.data.label);
    const categoryLabel = normalizeFocusText(node.data.categoryLabel);
    const description = normalizeFocusText(node.data.description);
    return candidates.some((candidate) => (
      label.includes(candidate)
      || candidate.includes(label)
      || categoryLabel.includes(candidate)
      || description.includes(candidate)
    ));
  });
}

// ── Main hook ──────────────────────────────────────────────────

export function useKnowledgeGraph(focusLabel: string = "") {
  const [nodes, setNodes] = useState<Node<KnowledgeMapNodeData>[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selectedNode, setSelectedNode] = useState<Node<KnowledgeMapNodeData> | null>(null);
  const [error, setError] = useState("");
  const mountedRef = useRef(true);
  const appliedFocusRef = useRef("");

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const fetchGraph = useCallback(async () => {
    try {
      // Use hierarchical API with levels=2 for cleaner visualization
      const res = await http.get("/api/visualization/knowledge-graph/hierarchical", {
        params: { levels: 2 },
      });
      if (!mountedRef.current) return;

      const apiNodes: HierarchicalNode[] = res.data?.nodes || [];
      const apiEdges: HierarchicalEdge[] = res.data?.edges || [];
      if (apiNodes.length > 0) {
        const map = buildHierarchicalMap(apiNodes, apiEdges);
        setNodes(map.nodes);
        setEdges(toReactEdges(map.edges));
        setError("");
      } else {
        setNodes([]);
        setEdges([]);
      }

      setSelectedNode((current) => {
        if (!current) return null;
        return apiNodes.find((n) => n.id === current.id) ? current : null;
      });
    } catch (error: unknown) {
      if (!mountedRef.current) return;
      setNodes([]);
      setEdges([]);
      setSelectedNode(null);
      setError(getErrorMessage(error, "知识图谱数据加载失败"));
    }
  }, []);

  useEffect(() => {
    void fetchGraph();
  }, [fetchGraph]);

  useEffect(() => {
    if (!focusLabel || appliedFocusRef.current === focusLabel) return;
    const focusedNode = findFocusedNode(nodes, focusLabel);
    if (!focusedNode) return;
    setSelectedNode(focusedNode);
    appliedFocusRef.current = focusLabel;
  }, [focusLabel, nodes]);

  const onNodesChange = useCallback((changes: NodeChange<Node<KnowledgeMapNodeData>>[]) => {
    setNodes((currentNodes) => applyNodeChanges(changes, currentNodes));
  }, []);

  return {
    nodes,
    edges,
    selectedNode,
    error,
    setSelectedNode,
    onNodesChange,
  };
}
