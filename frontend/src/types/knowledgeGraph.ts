export type KnowledgeGraphEdge = {
  source: string;
  target: string;
  relation: string;
};

export type KnowledgeGraphNodeKind = "root" | "level1" | "level2";

export type KnowledgeMapNodeData = Record<string, unknown> & {
  label: string;
  category: string;
  categoryLabel: string;
  description: string;
  kind: KnowledgeGraphNodeKind;
  accent: string;
  border: string;
  labelSide?: "left" | "right" | "top" | "bottom";
  highlight?: "selected" | "related" | "dimmed" | "normal";
  childCount?: number;
  icon?: string;
};

