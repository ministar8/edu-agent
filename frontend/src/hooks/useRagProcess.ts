import { useCallback, useEffect, useRef, useState } from "react";

import { getErrorMessage } from "@/lib/errors";
import { http } from "@/lib/http";
import type { RAGStep, RAGTrace } from "@/types/rag";

export function useRagProcess() {
  const [query, setQuery] = useState("");
  const [collection, setCollection] = useState("data_structure");
  const [steps, setSteps] = useState<RAGStep[]>([]);
  const [trace, setTrace] = useState<RAGTrace | null>(null);
  const [resultText, setResultText] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeStep, setActiveStep] = useState<number>(0);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const mountedRef = useRef(true);
  const abortRef = useRef<AbortController | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
      timersRef.current.forEach(clearTimeout);
      timersRef.current = [];
    };
  }, []);

  const searchRAG = useCallback(async () => {
    if (!query.trim()) return;
    // Cancel previous request and timers
    abortRef.current?.abort();
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
    const ac = new AbortController();
    abortRef.current = ac;

    setLoading(true);
    setActiveStep(0);
    setSteps([]);
    setTrace(null);
    setResultText("");

    try {
      const res = await http.get("/api/visualization/rag-process", {
        params: { query, collection },
        signal: ac.signal,
      });

      if (!mountedRef.current || ac.signal.aborted) return;

      const resultSteps = (res.data.steps || []) as RAGStep[];
      const resultTrace = (res.data.trace || null) as RAGTrace | null;
      const resultTextVal = (res.data.result_text || "") as string;

      // Set trace and result immediately
      setTrace(resultTrace);
      setResultText(resultTextVal);

      // Animate steps one by one
      for (let i = 0; i < resultSteps.length; i++) {
        if (!mountedRef.current || ac.signal.aborted) break;
        await new Promise((resolve) => {
          const id = setTimeout(resolve, 600);
          timersRef.current.push(id);
        });
        if (!mountedRef.current || ac.signal.aborted) break;
        setSteps(resultSteps.slice(0, i + 1));
        setActiveStep(i + 1);
      }
    } catch (error: unknown) {
      if (!mountedRef.current || ac.signal.aborted) return;
      if (error instanceof DOMException && error.name === "AbortError") return;
      const msg = getErrorMessage(error, "RAG 检索过程加载失败");
      setSteps([{ step: 0, name: "错误", data: msg, type: "input" }]);
    } finally {
      if (mountedRef.current && !ac.signal.aborted) setLoading(false);
    }
  }, [collection, query]);

  return { query, collection, steps, trace, resultText, loading, activeStep, setQuery, setCollection, searchRAG };
}
