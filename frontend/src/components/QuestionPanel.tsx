"use client";

import { useState } from "react";
import axios from "axios";

import { API_BASE_URL } from "@/lib/api";

type Difficulty = "basic" | "medium" | "hard" | "mixed";

const difficultyOptions: { value: Difficulty; label: string }[] = [
  { value: "mixed", label: "混合难度" },
  { value: "basic", label: "基础" },
  { value: "medium", label: "中等" },
  { value: "hard", label: "困难" },
];

const topicSuggestions = [
  "Python基础",
  "数据结构",
  "面向对象编程",
  "函数与模块",
  "文件操作",
  "异常处理",
  "装饰器与生成器",
  "机器学习基础",
];

export default function QuestionPanel() {
  const [topic, setTopic] = useState("");
  const [count, setCount] = useState(3);
  const [difficulty, setDifficulty] = useState<Difficulty>("mixed");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string>("");

  const generate = async () => {
    if (!topic.trim()) return;
    setLoading(true);
    setResult("");

    try {
      const res = await axios.post(`${API_BASE_URL}/api/questions/generate`, {
        topic,
        count,
        difficulty,
      }, {
        timeout: 120000,
      });
      setResult(res.data.raw);
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : String(error);
      setResult(`出题失败: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* 表单区 */}
      <div className="border-b bg-white p-6">
        <h2 className="text-lg font-bold text-gray-800 mb-4">📝 题目生成</h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* 知识点 */}
          <div>
            <label className="block text-sm font-medium text-gray-600 mb-1">知识点</label>
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="如：Python装饰器"
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <div className="flex flex-wrap gap-1 mt-2">
              {topicSuggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => setTopic(s)}
                  className="text-xs px-2 py-1 bg-blue-50 text-blue-600 rounded hover:bg-blue-100 transition"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* 数量 */}
          <div>
            <label className="block text-sm font-medium text-gray-600 mb-1">题目数量</label>
            <input
              type="number"
              min={1}
              max={10}
              value={count}
              onChange={(e) => setCount(Math.max(1, Math.min(10, Number(e.target.value))))}
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* 难度 */}
          <div>
            <label className="block text-sm font-medium text-gray-600 mb-1">难度</label>
            <div className="flex gap-2">
              {difficultyOptions.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setDifficulty(opt.value)}
                  className={`px-3 py-2 rounded-lg text-sm transition ${
                    difficulty === opt.value
                      ? "bg-blue-600 text-white"
                      : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <button
          onClick={generate}
          disabled={loading || !topic.trim()}
          className="mt-4 bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition text-sm font-medium"
        >
          {loading ? "正在生成..." : "生成题目"}
        </button>
      </div>

      {/* 结果区 */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading && (
          <div className="text-center text-gray-400 mt-10">
            <div className="text-4xl mb-3">🤔</div>
            <p>Agent 正在检索题库并生成题目...</p>
          </div>
        )}

        {!loading && !result && (
          <div className="text-center text-gray-400 mt-10">
            <div className="text-4xl mb-3">📝</div>
            <p>选择知识点和难度，点击生成题目</p>
          </div>
        )}

        {!loading && result && (
          <div className="bg-white rounded-xl border p-6">
            <div className="whitespace-pre-wrap text-sm leading-relaxed">{result}</div>
          </div>
        )}
      </div>
    </div>
  );
}
