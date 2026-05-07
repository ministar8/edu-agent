"use client";

import { useQuestionGeneration } from "@/hooks/useQuestionGeneration";
import type { QuestionPanelProps } from "@/types/question";
import { QuestionForm } from "./QuestionForm";
import { QuestionResult } from "./QuestionResult";
import { QuestionStrategyCard } from "./QuestionStrategyCard";

export default function QuestionPanel({ state, setState }: QuestionPanelProps) {
  const { generate, updateState } = useQuestionGeneration({ state, setState });

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-6 text-slate-800">
      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <QuestionForm state={state} onChange={updateState} onGenerate={() => void generate()} />
        <QuestionStrategyCard />
      </div>
      <QuestionResult state={state} />
    </div>
  );
}
