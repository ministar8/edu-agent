import { memo } from "react";

import type { QuestionPanelState, StructuredQuestion, WrongQuestion } from "@/types/question";

type QuestionResultProps = {
  state: QuestionPanelState;
  onGradeQuestion: (index: number) => void;
  onUpdateAnswer: (index: number, answer: string) => void;
  onLoadWrong: () => void;
  onWeakPointPractice: () => void;
  onSwitchTab: (tab: "generate" | "wrong") => void;
  onRedoWrongQuestion: (qId: number) => void;
  onRedoAnswerChange: (qId: number, answer: string) => void;
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
    <div className={`rounded-2xl border p-5 transition-all shadow-sm ${
      isGraded && question.isWrong ? "border-red-200 bg-red-50/20" :
      isGraded && !question.isWrong ? "border-green-200 bg-green-50/20" :
      "border-slate-200 bg-white hover:border-slate-300"
    }`}>
      {/* Header */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="rounded-lg bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
          题目{index + 1}
        </span>
        <span className="rounded-lg bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
          {question.question_type}
        </span>
        <span className="rounded-lg bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
          {getDifficultyLabel(question.difficulty)}
        </span>
        <span className="rounded-lg bg-amber-50 border border-amber-200/50 px-2 py-0.5 text-[10px] font-medium text-amber-700">
          闭环：生成 → 批改 → 反馈
        </span>
        {isGraded && (
          <span className={`ml-auto rounded-lg px-2 py-0.5 text-xs font-medium ${
            question.isWrong ? "bg-red-100 text-red-700" : "bg-green-100 text-green-700"
          }`}>
            {question.isWrong ? "需巩固" : "已掌握"}{question.gradingScore != null ? ` · ${question.gradingScore}分` : ""}
          </span>
        )}
      </div>

      {/* Stem */}
      <div className="mb-3 text-sm leading-6 text-slate-800 whitespace-pre-wrap font-medium">
        {question.stem}
      </div>

      {/* Answer input */}
      <div className="mb-3">
        <textarea
          className="w-full rounded-xl border border-stone-200 bg-stone-50 px-3 py-2 text-sm text-stone-700 placeholder:text-stone-400 focus:border-emerald-300 focus:outline-none focus:ring-1 focus:ring-emerald-200 disabled:opacity-80 disabled:bg-slate-50"
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
          AI 智能判分批改中...
        </span>
      )}

      {/* Grading Score Breakdown (visual) */}
      {isGraded && question.gradingScore != null && (
        <div className="mt-3 flex items-center gap-2 border-t border-dashed border-slate-100 pt-3">
          <span className="text-xs text-slate-500 font-medium">答分比对：</span>
          <div className="h-2 w-24 rounded-full bg-slate-100 overflow-hidden">
            <div className={`h-full rounded-full transition-all ${
              question.isWrong ? "bg-red-500" : "bg-emerald-500"
            }`} style={{ width: `${question.gradingScore}%` }} />
          </div>
          <span className="text-xs font-bold text-slate-700">{question.gradingScore}分</span>
        </div>
      )}

      {/* Grading feedback */}
      {isGraded && question.gradingFeedback && (
        <div className="mt-2 rounded-xl bg-slate-50 px-3 py-2.5 text-xs text-slate-600 leading-relaxed border border-slate-100">
          <div className="font-semibold text-slate-700 mb-1 flex items-center gap-1">
            <span className="inline-block w-1 h-3 rounded-full bg-blue-500" />
            AI 批改评语：
          </div>
          {question.gradingFeedback}
        </div>
      )}

      {/* Standard answer (reference) */}
      {isGraded && question.answer && (
        <div className="mt-2 rounded-xl bg-green-50/50 px-3 py-2.5 text-xs text-green-800 border border-green-100/50">
          <span className="font-semibold text-green-900 block mb-1">参考答案：</span>
          <div className="whitespace-pre-wrap">{question.answer}</div>
        </div>
      )}

      {/* Explanation (show after grading) */}
      {isGraded && question.explanation && (
        <div className="mt-2 rounded-xl bg-amber-50/50 px-3 py-2.5 text-xs text-amber-800 border border-amber-100/50">
          <span className="font-semibold text-amber-900 block mb-1">考点解析：</span>
          <div className="whitespace-pre-wrap">{question.explanation}</div>
        </div>
      )}
    </div>
  );
}

function WrongQuestionCard({
  q,
  onRedo,
  onRedoAnswerChange,
}: {
  q: WrongQuestion;
  onRedo: (qId: number) => void;
  onRedoAnswerChange: (qId: number, answer: string) => void;
}) {
  const isRedoing = q.redoStatus === "loading";
  const isRedone = q.redoStatus === "done";

  return (
    <div className={`rounded-2xl border p-5 transition-colors ${
      isRedone && !q.redoIsWrong ? "border-green-200 bg-green-50/20" : "border-red-200 bg-red-50/20"
    }`}>
      <div className="mb-2 flex items-center gap-2">
        <span className={`rounded-lg px-2 py-0.5 text-xs font-medium ${
          isRedone && !q.redoIsWrong ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
        }`}>
          {isRedone && !q.redoIsWrong ? "已掌握" : "错题"}
        </span>
        <span className="rounded-lg bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
          {q.question_type || "未知类型"}
        </span>
        <span className="text-xs text-slate-400">{q.created_at?.slice(0, 10)}</span>
        {q.grading_score !== null && (
          <span className="text-xs text-red-600">{q.grading_score}分</span>
        )}
        {q.redo_count > 0 && (
          <span className="rounded-lg bg-emerald-50 px-1.5 py-0.5 text-[10px] text-emerald-600">
            重做{q.redo_count}次
          </span>
        )}
      </div>
      <div className="text-sm leading-6 text-slate-800 whitespace-pre-wrap">{q.stem}</div>

      {/* Error analysis */}
      {q.error_analysis && (
        <div className="mt-2 rounded-xl bg-purple-50 px-3 py-2 text-xs text-purple-800">
          <span className="font-medium">错因分析：</span>{q.error_analysis}
        </div>
      )}

      {/* Standard answer & explanation */}
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

      {/* Redo section */}
      {!isRedone && (
        <div className="mt-3 border-t border-red-100 pt-3">
          <div className="mb-2 text-xs font-medium text-slate-600">重新作答</div>
          <textarea
            className="w-full rounded-xl border border-stone-200 bg-white px-3 py-2 text-sm text-stone-700 placeholder:text-stone-400 focus:border-emerald-300 focus:outline-none focus:ring-1 focus:ring-emerald-200"
            rows={2}
            placeholder="输入你的新答案..."
            value={q.redoAnswer || ""}
            onChange={(e) => onRedoAnswerChange(q.id, e.target.value)}
            disabled={isRedoing}
          />
          <button
            onClick={() => onRedo(q.id)}
            disabled={isRedoing || !(q.redoAnswer || "").trim()}
            className="mt-2 rounded-xl bg-orange-500 px-4 py-1.5 text-xs font-medium text-white hover:bg-orange-600 disabled:bg-stone-300 disabled:text-stone-500 transition-colors"
          >
            {isRedoing ? "批改中..." : "提交重做"}
          </button>
        </div>
      )}

      {/* Redo result */}
      {isRedone && (
        <div className="mt-3 border-t border-slate-100 pt-3">
          <div className="flex items-center gap-2 mb-1">
            <span className={`rounded-lg px-2 py-0.5 text-xs font-medium ${
              q.redoIsWrong ? "bg-red-100 text-red-700" : "bg-green-100 text-green-700"
            }`}>
              {q.redoIsWrong ? `重做错误 · ${q.redoScore}分` : `重做正确 · ${q.redoScore}分`}
            </span>
          </div>
          {q.redoFeedback && (
            <div className="rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600">{q.redoFeedback}</div>
          )}
          {q.redoIsWrong && q.redoErrorAnalysis && (
            <div className="mt-1 rounded-xl bg-purple-50 px-3 py-2 text-xs text-purple-800">
              <span className="font-medium">错因分析：</span>{q.redoErrorAnalysis}
            </div>
          )}
          {!q.redoIsWrong && (
            <div className="mt-1 text-xs text-emerald-600">恭喜！你已掌握此题，掌握度已更新。</div>
          )}
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
  onRedoWrongQuestion,
  onRedoAnswerChange,
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
                <WrongQuestionCard key={q.id} q={q} onRedo={onRedoWrongQuestion} onRedoAnswerChange={onRedoAnswerChange} />
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