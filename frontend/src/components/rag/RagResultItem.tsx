import { memo } from "react";

import type { RAGResult } from "@/types/rag";

type RagResultItemProps = {
  result: RAGResult;
  index: number;
};

function RagResultItemComponent({ result, index }: RagResultItemProps) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-4">
      <span className="rounded-xl bg-slate-100 px-2.5 py-1 text-xs font-mono text-slate-600">
        #{index + 1}
      </span>
      <div className="min-w-0 flex-1">
        <p className="line-clamp-3 text-sm leading-6 text-slate-700">
          {result.content?.slice(0, 200)}...
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-400">
            来源: {result.metadata?.source_file || "未知"}
          </span>
          {result.score !== undefined && (
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                result.score > 0.8
                  ? "bg-emerald-100 text-emerald-700"
                  : result.score > 0.5
                  ? "bg-amber-100 text-amber-700"
                  : "bg-rose-100 text-rose-700"
              }`}
            >
              相似度: {result.score.toFixed(4)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export const RagResultItem = memo(RagResultItemComponent);
