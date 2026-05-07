import { useCallback, useState } from "react";

import { getErrorMessage } from "@/lib/errors";
import { http } from "@/lib/http";
import type { RAGStep } from "@/types/rag";

export function useRagProcess() {
  const [query, setQuery] = useState("");
  const [collection, setCollection] = useState("data_structure");
  const [steps, setSteps] = useState<RAGStep[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeStep, setActiveStep] = useState<number>(0);

  const searchRAG = useCallback(async () => {
    if (!query.trim()) return;
    setLoading(true);
    setActiveStep(0);
    setSteps([]);

    try {
      const res = await http.get("/api/visualization/rag-process", {
        params: { query, collection },
      });

      const resultSteps = res.data.steps as RAGStep[];
      for (let i = 0; i < resultSteps.length; i++) {
        await new Promise((resolve) => setTimeout(resolve, 600));
        setSteps(resultSteps.slice(0, i + 1));
        setActiveStep(i + 1);
      }
    } catch (error: unknown) {
      const msg = getErrorMessage(error, "RAG 检索过程加载失败");
      setSteps([
        {
          step: 0,
          name: "错误",
          data: msg,
          type: "input",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [collection, query]);

  return {
    query,
    collection,
    steps,
    loading,
    activeStep,
    setQuery,
    setCollection,
    searchRAG,
  };
}
