import { memo } from "react";

import type { QuestionPanelState } from "@/types/question";

type QuestionResultProps = {
  state: QuestionPanelState;
};

function QuestionResultComponent({ state }: QuestionResultProps) {
  if (!state.loading && !state.result) {
    return null;
  }

  return (
    <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
      {state.loading && (
        <div className="py-12 text-center text-slate-400">
          <div className="mb-3 text-4xl">🤔</div>
          <p>正在生成 408 练习题...</p>
        </div>
      )}

      {!state.loading && state.result && (
        <div className="rounded-[24px] border border-slate-200 bg-slate-50 p-6">
          <div className="mb-4 flex items-center justify-between gap-4">
            <div>
              <h4 className="text-base font-semibold text-slate-800">生成结果</h4>
              <p className="mt-1 text-sm text-slate-500">已根据当前配置完成题目生成</p>
            </div>
            <span className="rounded-full bg-white px-3 py-1 text-xs font-medium text-slate-500">
              Topic: {state.resultTopic || state.topic}
            </span>
          </div>
          <div className="max-h-[52vh] overflow-y-auto whitespace-pre-wrap rounded-2xl bg-white px-5 py-4 text-sm leading-7 text-slate-700 shadow-sm">
            {state.result}
          </div>
        </div>
      )}
    </section>
  );
}

export const QuestionResult = memo(QuestionResultComponent);
