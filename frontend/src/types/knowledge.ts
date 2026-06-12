export interface Collection {
  name: string;
  count: number;
}

export interface UploadResultItem {
  filename: string;
  chunk_count: number;
  graph_nodes: number;
  graph_edges: number;
  success: boolean;
  error?: string;
}

export interface UploadResult {
  results?: UploadResultItem[];
  error?: string;
}

export type KnowledgeCategory = {
  value: string;
  label: string;
};
