import { useCallback } from "react";

import { getErrorMessage } from "@/lib/errors";
import { http } from "@/lib/http";
import type { QuestionPanelState } from "@/types/question";

type UseQuestionGenerationParams = {
  state: QuestionPanelState;
  setState: React.Dispatch<React.SetStateAction<QuestionPanelState>>;
};

export function useQuestionGeneration({ state, setState }: UseQuestionGenerationParams) {
  const updateState = useCallback((patch: Partial<QuestionPanelState>) => {
    setState((prev) => ({ ...prev, ...patch }));
  }, [setState]);

  const generate = useCallback(async () => {
    const currentTopic = state.topic.trim();
    if (!currentTopic || state.loading) return;

    updateState({ loading: true, result: "", resultTopic: currentTopic });

    try {
      const res = await http.post("/api/questions/generate", {
        topic: currentTopic,
        count: Math.max(1, Math.min(5, state.count)),
        difficulty: state.difficulty,
      }, {
        timeout: 150000,
      });
      updateState({ result: res.data.raw || "未返回生成结果。" });
    } catch (error: unknown) {
      const msg = getErrorMessage(error, "出题请求失败");
      updateState({ result: `出题失败: ${msg}` });
    } finally {
      updateState({ loading: false });
    }
  }, [state.count, state.difficulty, state.loading, state.topic, updateState]);

  return { generate, updateState };
}
