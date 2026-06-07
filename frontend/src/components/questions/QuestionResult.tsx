import { memo } from "react";

import type { QuestionPanelState, StructuredQuestion, WrongQuestion } from "@/types/question";

type QuestionResultProps = {
  state: QuestionPanelState;
  onGradeQuestion: (index: number) => void;
  onUpdateAnswer: (index: number, answer: string) => void;
  onLoadWrong: () => void;
  onWeakPointPractice: () => void;
  onSwitchTab: (tab: "generate" | "wrong") => void;
};

const DIFFICULTY_LABELS: Record<number, string> = {
  1.0: "基础",
  1.3: "理解",
  1.6: "综合",
  2.0: "高级",
};

function getDifficultyLabel(d: number): string {
  if (typeof d !== "number" || isNaN(d)) return "未知";
  return DIFFICULTY_LABELS[d] || (d <= 1.1 ? "基础" : d <= 1.4 ? "理解" : d <= 1.7 ? "综合" : "高级");
}

function QuestionCard({
  question,
  index,
  onGrade,
  onUpdateAnswer,
}: {
  question: StructuredQuestion;
  index: number;
  onGrade: () => void;
  onUpdateAnswer: (answer: string) => void;
}) {
  const isGrading = question.gradingStatus === "loading";
  const isGraded = question.gradingStatus === "done";

  return (
    <div className={`rounded-2xl border p-5 transition-colors ${
      isGraded && question.isWrong ? "border-red-200 bg-red-50/30" :
      isGraded && !question.isWrong ? "border-green-200 bg-green-50/30" :
      "border-slate-200 bg-white"
    }`}>
      {/* Header */}
      <div className="mb-3 flex items-center gap-2">
        <span className="rounded-lg bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
          题目{index + 1}
        </span>
        <span className="rounded-lg bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
          {question.question_type}
        </span>
        <span className="rounded-lg bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
          {getDifficultyLabel(question.difficulty)}
        </span>
        {isGraded && (
          <span className={`ml-auto rounded-lg px-2 py-0.5 text-xs font-medium ${
            question.isWrong ? "bg-red-100 text-red-700" : "bg-green-100 text-green-700"
          }`}>
            {question.isWrong ? "错误" : "正确"}{question.gradingScore != null ? ` · ${question.gradingScore}分` : ""}
          </span>
        )}
      </div>

      {/* Stem */}
      <div className="mb-3 text-sm leading-6 text-slate-800 whitespace-pre-wrap">
        {question.stem}
      </div>

      {/* Answer input */}
      <div className="mb-3">
        <textarea
          className="w-full rounded-xl border border-stone-200 bg-stone-50 px-3 py-2 text-sm text-stone-700 placeholder:text-stone-400 focus:border-emerald-300 focus:outline-none focus:ring-1 focus:ring-emerald-200"
          rows={2}
          placeholder="输入你的答案..."
          value={question.userAnswer || ""}
          onChange={(e) => onUpdateAnswer(e.target.value)}
          disabled={isGrading || isGraded}
        />
      </div>

      {/* Grade button */}
      {!isGraded && question.id && (
        <button
          onClick={onGrade}
          disabled={isGrading || !question.userAnswer?.trim()}
          className="rounded-xl bg-emerald-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:bg-stone-300 disabled:text-stone-500 transition-colors"
        >
          {isGrading ? "批改中..." : "提交答案"}
        </button>
      )}
      {isGrading && (
        <span className="inline-flex items-center gap-1 text-xs text-emerald-600">
          <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          批改中...
        </span>
      )}

      {/* Grading feedback */}
      {isGraded && question.gradingFeedback && (
        <div className="mt-2 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
          {question.gradingFeedback}
        </div>
      )}

      {/* Explanation (show after grading) */}
      {isGraded && question.explanation && (
        <div className="mt-2 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">
          <span className="font-medium">解析：</span>{question.explanation}
        </div>
      )}
    </div>
  );
}

function WrongQuestionCard({ q }: { q: WrongQuestion }) {
  return (
    <div className="rounded-2xl border border-red-200 bg-red-50/20 p-5">
      <div className="mb-2 flex items-center gap-2">
        <span className="rounded-lg bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">错题</span>
        <span className="rounded-lg bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
          {q.question_type || "未知类型"}
        </span>
        <span className="text-xs text-slate-400">{q.created_at?.slice(0, 10)}</span>
        {q.grading_score !== null && (
          <span className="ml-auto text-xs text-red-600">{q.grading_score}分</span>
        )}
      </div>
      <div className="text-sm leading-6 text-slate-800 whitespace-pre-wrap">{q.stem}</div>
      {q.standard_answer && (
        <div className="mt-2 rounded-xl bg-green-50 px-3 py-2 text-xs text-green-800">
          <span className="font-medium">标准答案：</span>{q.standard_answer}
        </div>
      )}
      {q.explanation && (
        <div className="mt-1 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">
          <span className="font-medium">解析：</span>{q.explanation}
        </div>
      )}
    </div>
  );
}

function QuestionResultComponent({
  state,
  onGradeQuestion,
  onUpdateAnswer,
  onLoadWrong,
  onWeakPointPractice,
  onSwitchTab,
}: QuestionResultProps) {
  const hasContent = state.loading || state.result || state.wrongQuestions.length > 0;
  if (!hasContent && state.questions.length === 0) return null;

  return (
    <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
      {/* Tab bar */}
      <div className="mb-4 flex items-center gap-2">
        <button
          onClick={() => onSwitchTab("generate")}
          className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
            state.activeTab === "generate" ? "bg-emerald-100 text-emerald-700" : "text-stone-500 hover:bg-stone-100"
          }`}
        >
          出题结果
        </button>
        <button
          onClick={onLoadWrong}
          className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
            state.activeTab === "wrong" ? "bg-red-100 text-red-700" : "text-slate-500 hover:bg-slate-100"
          }`}
        >
          错题本
        </button>
        <button
          onClick={onWeakPointPractice}
          className="ml-auto rounded-lg bg-orange-100 px-3 py-1.5 text-xs font-medium text-orange-700 hover:bg-orange-200 transition-colors"
        >
          薄弱专项练习
        </button>
      </div>

      {/* Loading */}
      {state.loading && (
        <div className="py-12 text-center text-slate-400">
          <div className="mb-3 text-4xl">🤔</div>
          <p>正在生成 408 练习题...</p>
        </div>
      )}

      {/* Generate tab: structured question cards */}
      {!state.loading && state.activeTab === "generate" && (
        <>
          {state.questions.length > 0 ? (
            <div className="space-y-4">
              {state.questions.map((q, i) => (
                <QuestionCard
                  key={i}
                  question={q}
                  index={i}
                  onGrade={() => onGradeQuestion(i)}
                  onUpdateAnswer={(answer) => onUpdateAnswer(i, answer)}
                />
              ))}
            </div>
          ) : state.result ? (
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
          ) : null}
        </>
      )}

      {/* Wrong questions tab */}
      {state.activeTab === "wrong" && (
        <>
          {state.wrongLoading ? (
            <div className="py-8 text-center text-slate-400">加载错题中...</div>
          ) : state.wrongQuestions.length > 0 ? (
            <div className="space-y-4">
              {state.wrongQuestions.map((q) => (
                <WrongQuestionCard key={q.id} q={q} />
              ))}
            </div>
          ) : (
            <div className="py-8 text-center text-slate-400">暂无错题记录</div>
          )}
        </>
      )}
    </section>
  );
}

export const QuestionResult = memo(QuestionResultComponent);