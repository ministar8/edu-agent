export interface Collection {
  name: string;
  count: number;
}

export interface UploadResultItem {
  filename: string;
  chunk_count: number;
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
