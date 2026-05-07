import { memo } from "react";

function QuestionStrategyCardComponent() {
  return (
    <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
      <h3 className="text-lg font-semibold text-slate-900">生成策略</h3>
      <div className="mt-5 space-y-4 text-sm leading-6 text-slate-500">
        <div className="rounded-3xl bg-slate-50 p-4">
          系统会结合知识点、题目数量与难度，生成选择题、填空题、简答题或综合应用题。
        </div>
        <div className="rounded-3xl bg-slate-50 p-4">
          建议优先使用清晰、具体的知识点名称，以提升检索与生成质量。
        </div>
        <div className="rounded-3xl bg-slate-50 p-4">
          为保证生成稳定性，单次最多生成 5 题；如需更多题目，建议分多次生成。
        </div>
      </div>
    </section>
  );
}

export const QuestionStrategyCard = memo(QuestionStrategyCardComponent);
