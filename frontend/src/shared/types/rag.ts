export interface RAGResult {
  content: string;
  metadata: Record<string, unknown>;
  score: number;
}

export interface RAGStep {
  step: number;
  name: string;
  data: string | RAGResult[];
  type: string;
}

// ── Trace types for enhanced RAG visualization ──

export interface TracePolicy {
  threshold: number;
  coarse_k: number;
  effective_k: number;
  use_rerank: boolean;
  retrieval_depth: string;
  skip_bm25: boolean;
  skip_decompose: boolean;
  skip_hyde: boolean;
}

export interface RouteTraceItem {
  collection: string;
  route: string;
  route_query: string;
  hits: number;
  top_score: number;
  top_source: string;
}

export interface RouteSummary {
  total_routes: number;
  total_hits: number;
  route_count: Record<string, number>;
  collection_count: Record<string, number>;
  hits_by_route: Record<string, number>;
  hits_by_collection: Record<string, number>;
}

export interface DecompositionTrace {
  decomposed: boolean;
  sub_queries: string[];
}

export interface RerankTrace {
  enabled: boolean;
  top_score: number;
  kept: number;
}

export interface HyDETrace {
  skipped: boolean;
  triggered: boolean;
  added_count: number;
}

export interface KGTrace {
  skipped: boolean;
  used: boolean;
  category: string;
  nodes_count: number;
  edges_count: number;
  paths_count: number;
  sample_nodes: string[];
  sample_paths: string[];
  resolved_topics: string[];
  matched_candidates: string[];
  error: string;
}

export interface ScoreStats {
  top: number;
  avg: number;
  min: number;
  max: number;
}

export interface TraceCounts {
  raw: number;
  after_dedup: number;
  after_threshold: number;
  after_rerank: number;
  after_hyde: number;
  after_window: number;
  final: number;
}

export interface RAGTrace {
  policy: TracePolicy;
  routes: RouteTraceItem[];
  route_summary: RouteSummary;
  decomposition: DecompositionTrace;
  rerank: RerankTrace;
  hyde: HyDETrace;
  kg: KGTrace;
  counts: TraceCounts;
  score_stats: {
    after_threshold: ScoreStats;
    after_rerank: ScoreStats;
    after_hyde: ScoreStats;
    final: ScoreStats;
  };
  duration_ms: number;
}
