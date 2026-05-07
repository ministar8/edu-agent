export interface RAGResult {
  content: string;
  metadata: Record<string, string>;
  score: number;
}

export interface RAGStep {
  step: number;
  name: string;
  data: string | RAGResult[];
  type: string;
}
