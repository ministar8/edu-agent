import { useCallback, useRef } from "react";

import { getErrorMessage } from "@/lib/errors";
import { http } from "@/lib/http";
import type { QuestionPanelState, StructuredQuestion } from "@/types/question";

type UseQuestionGenerationParams = {
  state: QuestionPanelState;
  setState: React.Dispatch<React.SetStateAction<QuestionPanelState>>;
};

export function useQuestionGeneration({ state, setState }: UseQuestionGenerationParams) {
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
      batchId: res.data.batch_id || null,
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
      batchId: null,
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
      const newQuestions = [...prev.questions];
      newQuestions[questionIndex] = { ...q, gradingStatus: "loading" };
      return { ...prev, questions: newQuestions };
    });
    if (!qId) return;

    try {
      const res = await http.post(`/api/questions/${qId}/grade`, {
        user_answer: qAnswer,
      });

      setState((prev) => {
        const newQuestions = [...prev.questions];
        newQuestions[questionIndex] = {
          ...newQuestions[questionIndex],
          gradingStatus: "done",
          gradingScore: res.data.score,
          gradingFeedback: res.data.feedback,
          isWrong: res.data.is_wrong,
        };
        return { ...prev, questions: newQuestions };
      });
    } catch (error: unknown) {
      setState((prev) => {
        const newQuestions = [...prev.questions];
        newQuestions[questionIndex] = {
          ...newQuestions[questionIndex],
          gradingStatus: "idle",
        };
        return { ...prev, questions: newQuestions };
      });
    }
  }, [setState]);

  const updateQuestionAnswer = useCallback((questionIndex: number, answer: string) => {
    const newQuestions = [...state.questions];
    newQuestions[questionIndex] = { ...newQuestions[questionIndex], userAnswer: answer };
    updateState({ questions: newQuestions });
  }, [state.questions, updateState]);

  const loadWrongQuestions = useCallback(async () => {
    updateState({ wrongLoading: true });
    try {
      const res = await http.get("/api/questions/wrong", { params: { limit: 20 } });
      updateState({ wrongQuestions: res.data || [], wrongLoading: false, activeTab: "wrong" as const });
    } catch {
      updateState({ wrongLoading: false });
    }
  }, [updateState]);

  const weakPointPractice = useCallback(async () => {
    if (generatingRef.current) return;
    generatingRef.current = true;
    updateState({ loading: true, result: "", questions: [], batchId: null });

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

  return { generate, updateState, gradeQuestion, updateQuestionAnswer, loadWrongQuestions, weakPointPractice };
}
