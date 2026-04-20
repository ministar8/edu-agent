"use client";

import { useState } from "react";
import axios from "axios";

import { API_BASE_URL } from "@/lib/api";

interface RAGResult {
  content: string;
  metadata: Record<string, string>;
  score: number;
}

interface RAGStep {
  step: number;
  name: string;
  data: string | RAGResult[];
  type: string;
}

const stepIcons: Record<string, string> = {
  input: "📝",
  transform: "🔄",
  search: "🔍",
  results: "📊",
};

const stepColors: Record<string, string> = {
  input: "border-blue-400 bg-blue-50",
  transform: "border-yellow-400 bg-yellow-50",
  search: "border-green-400 bg-green-50",
  results: "border-purple-400 bg-purple-50",
};

export default function RAGProcessPanel() {
  const [query, setQuery] = useState("");
  const [collection, setCollection] = useState("general");
  const [steps, setSteps] = useState<RAGStep[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeStep, setActiveStep] = useState<number>(0);

  const searchRAG = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setActiveStep(0);
    setSteps([]);

    try {
      const res = await axios.get(`${API_BASE_URL}/api/visualization/rag-process`, {
        params: { query, collection },
      });

      const resultSteps = res.data.steps as RAGStep[];
      // 逐步展示，模拟动画效果
      for (let i = 0; i < resultSteps.length; i++) {
        await new Promise((r) => setTimeout(r, 600));
        setSteps(resultSteps.slice(0, i + 1));
        setActiveStep(i + 1);
      }
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : String(error);
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
  };

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h2 className="text-xl font-bold text-gray-800 mb-2">RAG检索过程可视化</h2>
      <p className="text-sm text-gray-500 mb-6">
        输入查询，实时展示RAG检索的每个步骤：查询改写 → 向量检索 → 结果排序
      </p>

      {/* Search Input */}
      <div className="bg-white rounded-xl border p-4 mb-6 flex gap-3">
        <select
          value={collection}
          onChange={(e) => setCollection(e.target.value)}
          className="border rounded-lg px-3 py-2 text-sm w-40"
        >
          <option value="general">通用教材</option>
          <option value="questions">题库</option>
          <option value="answers">标准答案</option>
          <option value="learning_paths">学习路径</option>
        </select>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && searchRAG()}
          placeholder="输入检索查询，如：Python装饰器的工作原理"
          className="flex-1 border rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={searchRAG}
          disabled={loading}
          className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm"
        >
          {loading ? "检索中..." : "检索"}
        </button>
      </div>

      {/* RAG Pipeline Steps */}
      <div className="space-y-4">
        {steps.map((step, index) => (
          <div
            key={step.step}
            className={`border-2 rounded-xl p-4 transition-all duration-500 ${
              stepColors[step.type] || "border-gray-300 bg-gray-50"
            } ${activeStep === index + 1 ? "rag-step-active" : ""}`}
          >
            <div className="flex items-center gap-3 mb-3">
              <span className="text-2xl">{stepIcons[step.type] || "📌"}</span>
              <div>
                <div className="font-bold text-gray-800">
                  Step {step.step}: {step.name}
                </div>
                <div className="text-xs text-gray-500">
                  {step.type === "input" && "用户输入的原始查询"}
                  {step.type === "transform" && "LLM改写查询以提升检索效果"}
                  {step.type === "search" && "在向量数据库中检索相似文档"}
                  {step.type === "results" && "检索到的相关文档及相似度分数"}
                </div>
              </div>
              {activeStep === index + 1 && (
                <span className="ml-auto text-green-500 text-sm font-medium">✓ 完成</span>
              )}
            </div>

            <div className="bg-white/60 rounded-lg p-3 text-sm">
              {step.type === "results" && Array.isArray(step.data) ? (
                <div className="space-y-2">
                  {(step.data as RAGResult[]).map((result, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-3 p-2 bg-white rounded-lg border"
                    >
                      <span className="bg-blue-100 text-blue-700 text-xs px-2 py-1 rounded font-mono">
                        #{i + 1}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-gray-700 text-sm line-clamp-2">
                          {result.content?.slice(0, 200)}...
                        </p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-xs text-gray-400">
                            来源: {result.metadata?.source_file || "未知"}
                          </span>
                          {result.score !== undefined && (
                            <span
                              className={`text-xs px-2 py-0.5 rounded ${
                                result.score > 0.8
                                  ? "bg-green-100 text-green-700"
                                  : result.score > 0.5
                                  ? "bg-yellow-100 text-yellow-700"
                                  : "bg-red-100 text-red-700"
                              }`}
                            >
                              相似度: {result.score.toFixed(4)}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-gray-700 font-mono">{String(step.data)}</p>
              )}
            </div>
          </div>
        ))}

        {/* Empty State */}
        {steps.length === 0 && !loading && (
          <div className="text-center py-16 text-gray-400">
            <div className="text-5xl mb-3">🔍</div>
            <p>输入查询开始RAG检索过程可视化</p>
          </div>
        )}

        {/* Loading Animation */}
        {loading && steps.length === 0 && (
          <div className="text-center py-8">
            <div className="inline-flex gap-2 text-3xl">
              <span className="animate-bounce" style={{ animationDelay: "0s" }}>📝</span>
              <span className="animate-bounce" style={{ animationDelay: "0.15s" }}>🔄</span>
              <span className="animate-bounce" style={{ animationDelay: "0.3s" }}>🔍</span>
              <span className="animate-bounce" style={{ animationDelay: "0.45s" }}>📊</span>
            </div>
            <p className="text-gray-500 mt-2">正在执行RAG检索管线...</p>
          </div>
        )}
      </div>
    </div>
  );
}
