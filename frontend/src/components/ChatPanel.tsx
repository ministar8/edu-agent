"use client";

import { useState, useRef, useEffect } from "react";

import { API_BASE_URL } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
  agentName?: string;
  sources?: string[];
  timestamp: Date;
}

const agentColors: Record<string, string> = {
  knowledge_agent: "bg-green-50 border-green-200",
  question_agent: "bg-pink-50 border-pink-200",
  grading_agent: "bg-purple-50 border-purple-200",
  path_agent: "bg-orange-50 border-orange-200",
  supervisor: "bg-blue-50 border-blue-200",
};

const agentLabels: Record<string, string> = {
  knowledge_agent: "知识点检索Agent",
  question_agent: "题目生成Agent",
  grading_agent: "批改评估Agent",
  path_agent: "学习路径推荐Agent",
  supervisor: "Supervisor调度",
};

const toolLabels: Record<string, string> = {
  search_knowledge_base: "检索知识库",
  search_question_templates: "检索题库",
  search_standard_answer: "检索标准答案",
  search_learning_path: "检索学习路径",
  query_knowledge_graph: "查询知识图谱",
};

export default function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [streamingAgent, setStreamingAgent] = useState("");
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    const userContent = input;
    const userMsg: Message = {
      role: "user",
      content: userContent,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);
    setStreamingText("");
    setStreamingAgent("supervisor");
    setActiveTool(null);

    try {
      const res = await fetch(`${API_BASE_URL}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userContent, thread_id: "default" }),
      });

      if (!res.ok || !res.body) {
        throw new Error(`HTTP ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let agentName = "supervisor";
      let fullText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            // 事件类型行，跳过，下一行是 data
            continue;
          }
          if (!line.startsWith("data: ")) continue;

          try {
            const data = JSON.parse(line.slice(6));

            if (data.agent_name) {
              agentName = data.agent_name;
              setStreamingAgent(agentName);
            }

            if (data.text) {
              fullText += data.text;
              setStreamingText(fullText);
            }

            if (data.tool_name) {
              if (data.status === "start") {
                setActiveTool(data.tool_name);
              } else {
                setActiveTool(null);
              }
            }
          } catch {
            // 忽略解析错误
          }
        }
      }

      // 流结束，将完整消息加入列表
      const assistantMsg: Message = {
        role: "assistant",
        content: fullText,
        agentName: agentName,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : String(error);
      const errorMsg: Message = {
        role: "assistant",
        content: `系统错误: ${msg}`,
        agentName: "system",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
      setStreamingText("");
      setStreamingAgent("");
      setActiveTool(null);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && !loading && (
          <div className="text-center text-gray-400 mt-20">
            <div className="text-6xl mb-4">🎓</div>
            <h3 className="text-xl font-bold text-gray-600">智能教学辅导系统</h3>
            <p className="mt-2">试试问我：</p>
            <div className="mt-4 space-y-2">
              {[
                "什么是Python装饰器？",
                "给我出3道Python基础题",
                "帮我批改这段代码",
                "我该怎么学机器学习？",
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => setInput(suggestion)}
                  className="block mx-auto px-4 py-2 bg-blue-50 text-blue-600 rounded-lg hover:bg-blue-100 transition text-sm"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[70%] rounded-xl px-4 py-3 ${
                msg.role === "user"
                  ? "chat-message-user"
                  : agentColors[msg.agentName || ""] || "chat-message-agent"
              }`}
            >
              {msg.agentName && msg.role === "assistant" && (
                <div className="text-xs font-medium text-gray-500 mb-1">
                  {agentLabels[msg.agentName] || msg.agentName}
                </div>
              )}
              <div className="whitespace-pre-wrap text-sm">{msg.content}</div>
              {msg.sources && msg.sources.length > 0 && (
                <div className="mt-2 pt-2 border-t border-gray-200">
                  <div className="text-xs text-gray-400">参考来源：</div>
                  {msg.sources.map((src, j) => (
                    <span
                      key={j}
                      className="inline-block text-xs bg-blue-100 text-blue-600 px-2 py-0.5 rounded mr-1 mt-1"
                    >
                      {src}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {/* 流式输出区域 */}
        {loading && (
          <div className="flex justify-start">
            <div
              className={`max-w-[70%] rounded-xl px-4 py-3 ${
                agentColors[streamingAgent] || "chat-message-agent"
              }`}
            >
              {streamingAgent && (
                <div className="text-xs font-medium text-gray-500 mb-1">
                  {agentLabels[streamingAgent] || streamingAgent}
                </div>
              )}

              {activeTool && (
                <div className="text-xs text-blue-500 mb-2 flex items-center gap-1">
                  <span className="animate-spin">⚙</span>
                  {toolLabels[activeTool] || activeTool}...
                </div>
              )}

              {streamingText ? (
                <div className="whitespace-pre-wrap text-sm">{streamingText}<span className="animate-pulse">▌</span></div>
              ) : (
                <div className="text-sm text-gray-500">
                  <span className="inline-flex gap-1">
                    <span className="animate-bounce">●</span>
                    <span className="animate-bounce" style={{ animationDelay: "0.1s" }}>●</span>
                    <span className="animate-bounce" style={{ animationDelay: "0.2s" }}>●</span>
                  </span>
                  {" "}Agent正在思考...
                </div>
              )}
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t bg-white p-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
            placeholder="输入你的问题..."
            className="flex-1 border rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={loading}
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition"
          >
            发送
          </button>
        </div>
      </div>
    </div>
  );
}
