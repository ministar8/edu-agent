import { memo } from "react";

import type { RAGStep } from "@/shared/types/rag";
import { RagStepCard } from "./RagStepCard";

type RagStepListProps = {
  steps: RAGStep[];
  loading: boolean;
  activeStep: number;
};

function RagStepListComponent({ steps, loading, activeStep }: RagStepListProps) {
  return (
    <section className="min-h-0 flex-1 overflow-y-auto rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
      <div className="space-y-4">
        {steps.map((step, index) => (
          <RagStepCard key={`${step.step}-${index}`} step={step} index={index} activeStep={activeStep} />
        ))}

        {steps.length === 0 && !loading && (
          <div className="py-16 text-center text-slate-400">
            <div className="mb-3 text-5xl">🔍</div>
            <p>输入查询开始 RAG 检索过程可视化</p>
          </div>
        )}

        {loading && steps.length === 0 && (
          <div className="py-10 text-center">
            <div className="inline-flex gap-2 text-3xl">
              <span className="animate-bounce" style={{ animationDelay: "0s" }}>📝</span>
              <span className="animate-bounce" style={{ animationDelay: "0.15s" }}>🔄</span>
              <span className="animate-bounce" style={{ animationDelay: "0.3s" }}>🔍</span>
              <span className="animate-bounce" style={{ animationDelay: "0.45s" }}>📊</span>
            </div>
            <p className="mt-3 text-slate-500">正在执行 RAG 检索管线...</p>
          </div>
        )}
      </div>
    </section>
  );
}

export const RagStepList = memo(RagStepListComponent);
