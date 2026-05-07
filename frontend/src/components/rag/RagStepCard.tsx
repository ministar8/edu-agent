import { memo } from "react";

import type { RAGResult, RAGStep } from "@/types/rag";
import { stepColors, stepDescriptions, stepIcons } from "./ragConfig";
import { RagResultItem } from "./RagResultItem";

type RagStepCardProps = {
  step: RAGStep;
  index: number;
  activeStep: number;
};

function RagStepCardComponent({ step, index, activeStep }: RagStepCardProps) {
  const isActive = activeStep === index + 1;

  return (
    <div
      className={`rounded-[24px] border p-5 transition-all duration-500 ${
        stepColors[step.type] || "border-slate-200 bg-slate-50"
      } ${isActive ? "ring-2 ring-slate-200" : ""}`}
    >
      <div className="mb-4 flex items-center gap-3">
        <span className="text-2xl">{stepIcons[step.type] || "📌"}</span>
        <div>
          <div className="text-base font-semibold text-slate-800">
            Step {step.step}: {step.name}
          </div>
          <div className="text-xs text-slate-500">
            {stepDescriptions[step.type] || "检索处理步骤"}
          </div>
        </div>
        {isActive && (
          <span className="ml-auto rounded-full bg-white px-3 py-1 text-xs font-medium text-emerald-600 shadow-sm">完成</span>
        )}
      </div>

      <div className="rounded-2xl bg-white/80 p-4 text-sm shadow-sm">
        {step.type === "results" && Array.isArray(step.data) ? (
          <div className="space-y-3">
            {(step.data as RAGResult[]).length === 0 && (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-700">
                未检索到可用于重排的相关文档。请确认该科目知识库已入库，或切换到更匹配的集合后重试。
              </div>
            )}
            {(step.data as RAGResult[]).map((result, resultIndex) => (
              <RagResultItem key={`${result.metadata?.source_file || "source"}-${resultIndex}`} result={result} index={resultIndex} />
            ))}
          </div>
        ) : (
          <p className="whitespace-pre-wrap leading-6 text-slate-700">{String(step.data || "暂无可展示内容")}</p>
        )}
      </div>
    </div>
  );
}

export const RagStepCard = memo(RagStepCardComponent);
