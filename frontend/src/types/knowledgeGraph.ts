export type KnowledgeGraphNode = {
  id: string;
  category: string;
  description: string;
};

export type KnowledgeGraphEdge = {
  source: string;
  target: string;
  relation: string;
};

export type ImportGraphNode = {
  name: string;
  category: string;
  description: string;
};

export type ImportGraphEdge = KnowledgeGraphEdge;
