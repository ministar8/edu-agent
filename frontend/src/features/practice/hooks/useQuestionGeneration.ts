import { useCallback, useRef } from "react";

import { useTrackingRefresh } from "@/shared/contexts/TrackingRefreshContext";
import { getErrorMessage } from "@/shared/lib/errors";
import { http } from "@/shared/lib/http";
import type { QuestionPanelState, StructuredQuestion, WrongQuestion } from "@/shared/types/question";

type UseQuestionGenerationParams = {
  state: QuestionPanelState;
  setState: React.Dispatch<React.SetStateAction<QuestionPanelState>>;
};

function updateAt<T>(items: T[], index: number, patch: Partial<T>) {
  return items.map((item, itemIndex) => (
    itemIndex === index ? { ...item, ...patch } : item
  ));
}

function updateById<T extends { id: number }>(items: T[], id: number, patch: Partial<T>) {
  return items.map((item) => (
    item.id === id ? { ...item, ...patch } : item
  ));
}

export function useQuestionGeneration({ state, setState }: UseQuestionGenerationParams) {
  const { triggerRefresh: triggerTrackingRefresh } = useTrackingRefresh();
  const generatingRef = useRef(false);

  const updateState = useCallback((patch: Partial<QuestionPanelState>) => {
    setState((prev) => ({ ...prev, ...patch }));
  }, [setState]);

  const handleGenerateResult = useCallback((res: { data: { raw?: string; questions?: StructuredQuestion[]; batch_id?: string } }, extraPatch?: Partial<QuestionPanelState>) => {
    const raw = res.data.raw || "未返回生成结果。";
    const questions: StructuredQuestion[] = (res.data.questions || []).map(
      (q: StructuredQuestion) => ({
        ...q,
        gradingStatus: "idle" as const,
        userAnswer: "",
      })
    );
    updateState({
      result: raw,
      questions,
      ...extraPatch,
    });
  }, [updateState]);

  const generate = useCallback(async () => {
    const currentTopic = state.topic.trim();
    if (!currentTopic || generatingRef.current) return;
    generatingRef.current = true;

    updateState({
      loading: true,
      result: "",
      resultTopic: currentTopic,
      questions: [],
    });

    try {
      const res = await http.post("/api/questions/generate", {
        topic: currentTopic,
        count: Math.max(1, Math.min(5, state.count)),
        difficulty: state.difficulty,
      }, {
        timeout: 150000,
      });
      handleGenerateResult(res);
    } catch (error: unknown) {
      const msg = getErrorMessage(error, "出题请求失败");
      updateState({ result: `出题失败: ${msg}` });
    } finally {
      updateState({ loading: false });
      generatingRef.current = false;
    }
  }, [state.count, state.difficulty, state.topic, updateState, handleGenerateResult]);

  const gradeQuestion = useCallback(async (questionIndex: number) => {
    // Use useRef-style pattern to safely get current state before async
    let qId: number | undefined;
    let qAnswer: string = "";
    setState((prev) => {
      const q = prev.questions[questionIndex];
      if (!q || !q.id || q.gradingStatus === "loading") return prev;
      qId = q.id;
      qAnswer = q.userAnswer || "";
      return { ...prev, questions: updateAt(prev.questions, questionIndex, { gradingStatus: "loading" }) };
    });
    if (!qId) return;

    try {
      const res = await http.post(`/api/questions/${qId}/grade`, {
        user_answer: qAnswer,
      });

      setState((prev) => {
        return {
          ...prev,
          questions: updateAt(prev.questions, questionIndex, {
            gradingStatus: "done",
            gradingScore: res.data.score,
            gradingFeedback: res.data.feedback,
            isWrong: res.data.is_wrong,
          }),
        };
      });
      triggerTrackingRefresh();
    } catch (error: unknown) {
      const msg = getErrorMessage(error, "批改失败");
      setState((prev) => {
        return {
          ...prev,
          questions: updateAt(prev.questions, questionIndex, {
            gradingStatus: "idle",
            gradingFeedback: msg,
          }),
        };
      });
    }
  }, [setState, triggerTrackingRefresh]);

  const updateQuestionAnswer = useCallback((questionIndex: number, answer: string) => {
    updateState({ questions: updateAt(state.questions, questionIndex, { userAnswer: answer }) });
  }, [state.questions, updateState]);

  const loadWrongQuestions = useCallback(async () => {
    updateState({ wrongLoading: true });
    try {
      const res = await http.get("/api/questions/wrong", { params: { limit: 20 } });
      updateState({ wrongQuestions: res.data || [], wrongLoading: false, activeTab: "wrong" as const });
    } catch (error: unknown) {
      const msg = getErrorMessage(error, "错题加载失败");
      updateState({ wrongLoading: false, result: `错题加载失败: ${msg}` });
    }
  }, [updateState]);

  const weakPointPractice = useCallback(async () => {
    if (generatingRef.current) return;
    generatingRef.current = true;
    updateState({ loading: true, result: "", questions: [] });

    try {
      const res = await http.post("/api/questions/weak-point-practice", {
        count: 3,
      }, {
        timeout: 150000,
      });
      handleGenerateResult(res, { activeTab: "generate" });
    } catch (error: unknown) {
      const msg = getErrorMessage(error, "薄弱练习失败");
      updateState({ result: `练习题生成失败: ${msg}` });
    } finally {
      updateState({ loading: false });
      generatingRef.current = false;
    }
  }, [updateState, handleGenerateResult]);

  const redoAnswerChange = useCallback((qId: number, answer: string) => {
    setState((prev) => ({
      ...prev,
      wrongQuestions: updateById(prev.wrongQuestions, qId, { redoAnswer: answer }),
    }));
  }, [setState]);

  const redoWrongQuestion = useCallback(async (qId: number) => {
    let answer = "";
    let shouldSubmit = false;
    setState((prev) => {
      const wq = prev.wrongQuestions.find((w) => w.id === qId);
      if (!wq || wq.redoStatus === "loading") return prev;
      answer = wq.redoAnswer || "";
      if (!answer.trim()) return prev;
      shouldSubmit = true;
      return {
        ...prev,
        wrongQuestions: updateById(prev.wrongQuestions, qId, { redoStatus: "loading" }),
      };
    });
    if (!shouldSubmit) return;

    try {
      const res = await http.post(`/api/questions/${qId}/grade`, {
        user_answer: answer,
      });

      setState((prev) => ({
        ...prev,
        wrongQuestions: prev.wrongQuestions.map((wrongQuestion): WrongQuestion => {
          if (wrongQuestion.id !== qId) return wrongQuestion;
          return {
            ...wrongQuestion,
            redoStatus: "done",
            redoScore: res.data.score,
            redoFeedback: res.data.feedback,
            redoIsWrong: res.data.is_wrong,
            redoErrorAnalysis: res.data.error_analysis || "",
            grading_score: res.data.is_wrong ? wrongQuestion.grading_score : res.data.score,
            error_analysis: res.data.error_analysis || wrongQuestion.error_analysis,
          };
        }),
      }));
      triggerTrackingRefresh();
    } catch (error: unknown) {
      const msg = getErrorMessage(error, "重练批改失败");
      setState((prev) => ({
        ...prev,
        wrongQuestions: updateById(prev.wrongQuestions, qId, {
          redoStatus: "idle",
          redoFeedback: msg,
        }),
      }));
    }
  }, [setState, triggerTrackingRefresh]);

  return { generate, updateState, gradeQuestion, updateQuestionAnswer, loadWrongQuestions, weakPointPractice, redoWrongQuestion, redoAnswerChange };
}
