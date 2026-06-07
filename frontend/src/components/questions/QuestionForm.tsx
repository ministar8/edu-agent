import { memo } from "react";

import type { QuestionPanelState } from "@/types/question";
import { difficultyOptions, topicSuggestions } from "./questionConfig";

type QuestionFormProps = {
  state: QuestionPanelState;
  onChange: (patch: Partial<QuestionPanelState>) => void;
  onGenerate: () => void;
};

function QuestionFormComponent({ state, onChange, onGenerate }: QuestionFormProps) {
  return (
    <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-xl font-semibold text-slate-900">练习题生成</h3>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            选择知识点、题目数量与难度，生成符合 408 考试题型的练习内容。
          </p>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
          Question Agent
        </span>
      </div>

      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        <div className="md:col-span-2 xl:col-span-1">
          <label className="mb-1.5 block text-sm font-medium text-slate-700">知识点</label>
          <input
            type="text"
            value={state.topic}
            onChange={(event) => onChange({ topic: event.target.value })}
            placeholder="如：操作系统-进程调度"
            maxLength={100}
            className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition focus:border-slate-400 focus:ring-4 focus:ring-slate-200/70"
          />
          <div className="mt-3 flex flex-wrap gap-2">
            {topicSuggestions.map((suggestion) => (
              <button
                key={suggestion}
                onClick={() => onChange({ topic: suggestion })}
                className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-200 hover:text-slate-800"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">题目数量</label>
          <input
            type="number"
            min={1}
            max={5}
            value={state.count}
            onChange={(event) => onChange({ count: Math.max(1, Math.min(5, Number(event.target.value))) })}
            className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition focus:border-slate-400 focus:ring-4 focus:ring-slate-200/70"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">难度</label>
          <div className="grid grid-cols-2 gap-2">
            {difficultyOptions.map((option) => (
              <button
                key={option.value}
                onClick={() => onChange({ difficulty: option.value })}
                className={`rounded-2xl px-3 py-3 text-sm font-medium transition ${
                  state.difficulty === option.value
                    ? "bg-slate-800 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-800"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <button
        onClick={onGenerate}
        disabled={state.loading || !state.topic.trim()}
        className="mt-6 rounded-2xl bg-slate-800 px-5 py-3 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {state.loading ? "正在生成..." : "生成题目"}
      </button>
    </section>
  );
}

export const QuestionForm = memo(QuestionFormComponent);
