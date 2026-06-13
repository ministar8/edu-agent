import { memo, useMemo } from "react";

import type { AgentStep, Governance } from "@/shared/types/chat";
import { agentLabels, toolLabels } from "./chatMeta";

type TeachingAnalysisPanelProps = {
  query?: string;
  answer: string;
  agentName?: string;
  sources?: string[];
  governance?: Governance;
  agentSteps?: AgentStep[];
  onOpenKnowledgeGraph?: (focus: string) => void;
  onGenerateSimilarPractice?: (topic: string) => void;
};

type DiagnosisLevel = "mastered" | "review" | "weak";

type KnowledgeDiagnosis = {
  name: string;
  subject: string;
  level: DiagnosisLevel;
  reason: string;
};

type TeachingTrace = {
  intent: string;
  subject: string;
  difficulty: string;
  strategy: string;
  knowledgePoints: KnowledgeDiagnosis[];
  evidenceItems: {
    title: string;
    snippet: string;
    score: number;
    reason: string;
  }[];
  timeline: {
    title: string;
    detail: string;
    status: "done" | "active";
  }[];
  learningPath: string[];
};

const subjectRules = [
  {
    subject: "操作系统",
    keywords: ["进程", "线程", "调度", "死锁", "信号量", "内存", "分页", "分段", "文件", "互斥", "同步", "PV"],
  },
  {
    subject: "数据结构",
    keywords: ["二叉树", "树", "图", "链表", "顺序表", "栈", "队列", "排序", "查找", "哈希", "B树", "算法"],
  },
  {
    subject: "计算机网络",
    keywords: ["TCP", "UDP", "IP", "HTTP", "DNS", "路由", "拥塞", "子网", "链路", "网络层", "传输层"],
  },
  {
    subject: "计算机组成原理",
    keywords: ["CPU", "Cache", "缓存", "指令", "补码", "浮点", "流水线", "存储器", "总线", "中断", "DMA"],
  },
];

const knowledgeRules = [
  { name: "进程同步", subject: "操作系统", keywords: ["同步", "信号量", "PV", "互斥", "临界区"] },
  { name: "死锁", subject: "操作系统", keywords: ["死锁", "银行家", "资源分配"] },
  { name: "进程调度", subject: "操作系统", keywords: ["调度", "时间片", "优先级", "FCFS", "SJF"] },
  { name: "内存管理", subject: "操作系统", keywords: ["内存", "分页", "分段", "页面置换", "虚拟内存"] },
  { name: "树与二叉树", subject: "数据结构", keywords: ["二叉树", "遍历", "树", "哈夫曼"] },
  { name: "图结构", subject: "数据结构", keywords: ["图", "最短路径", "拓扑", "生成树"] },
  { name: "排序算法", subject: "数据结构", keywords: ["排序", "快排", "归并", "堆排序"] },
  { name: "查找结构", subject: "数据结构", keywords: ["查找", "哈希", "散列", "B树"] },
  { name: "TCP/UDP", subject: "计算机网络", keywords: ["TCP", "UDP", "可靠传输", "三次握手"] },
  { name: "网络层", subject: "计算机网络", keywords: ["IP", "路由", "子网", "NAT"] },
  { name: "数据链路层", subject: "计算机网络", keywords: ["链路", "差错", "滑动窗口", "CSMA"] },
  { name: "存储系统", subject: "计算机组成原理", keywords: ["Cache", "缓存", "主存", "存储器"] },
  { name: "指令系统", subject: "计算机组成原理", keywords: ["指令", "寻址", "CISC", "RISC"] },
  { name: "CPU结构", subject: "计算机组成原理", keywords: ["CPU", "流水线", "控制器", "数据通路"] },
];

function includesAny(text: string, keywords: string[]) {
  const lower = text.toLowerCase();
  return keywords.some((keyword) => lower.includes(keyword.toLowerCase()));
}

function inferIntent(text: string) {
  if (includesAny(text, ["出题", "练习", "测试", "考考"])) return "练习生成";
  if (includesAny(text, ["批改", "答案", "为什么错", "得分"])) return "答案评估";
  if (includesAny(text, ["区别", "比较", "对比"])) return "概念对比";
  if (includesAny(text, ["怎么复习", "学习路径", "计划", "路线"])) return "学习规划";
  if (includesAny(text, ["是什么", "解释", "原理", "关系"])) return "概念解释";
  return "综合问答";
}

function inferSubject(text: string) {
  const matched = subjectRules
    .map((rule) => ({
      subject: rule.subject,
      score: rule.keywords.filter((keyword) => text.toLowerCase().includes(keyword.toLowerCase())).length,
    }))
    .sort((a, b) => b.score - a.score);
  return matched[0]?.score ? matched[0].subject : "408 综合知识";
}

function inferDifficulty(text: string, pointCount: number) {
  if (includesAny(text, ["综合", "设计", "分析", "证明"]) || pointCount >= 4) return "综合";
  if (includesAny(text, ["区别", "关系", "为什么", "过程"]) || pointCount >= 2) return "中等";
  return "基础";
}

function inferStrategy(intent: string, difficulty: string) {
  if (intent === "练习生成") return "先定位考点，再生成同类题并给出解析。";
  if (intent === "答案评估") return "先匹配标准答案，再指出缺漏和可得分点。";
  if (intent === "学习规划") return "先找薄弱知识点，再给出前置到后续的学习路径。";
  if (difficulty === "综合") return "先拆分子问题，再结合证据逐步推理。";
  return "先解释核心概念，再补充易混点和复习建议。";
}

function inferLearningPath(pointName: string, subject: string) {
  const pathMap: Record<string, string[]> = {
    "TCP/UDP": ["网络体系结构", "传输层", "TCP/UDP", "可靠传输", "拥塞控制"],
    "网络层": ["网络体系结构", "数据链路层", "网络层", "路由选择", "子网划分"],
    "数据链路层": ["网络体系结构", "数据链路层", "差错控制", "滑动窗口"],
    "进程同步": ["进程管理", "进程同步", "信号量", "经典同步问题", "死锁"],
    "死锁": ["进程管理", "进程同步", "死锁", "银行家算法"],
    "内存管理": ["进程管理", "内存管理", "分页分段", "虚拟内存", "页面置换"],
    "树与二叉树": ["线性结构", "树与二叉树", "二叉树遍历", "哈夫曼树"],
    "图结构": ["线性结构", "图结构", "最短路径", "最小生成树"],
    "排序算法": ["线性结构", "排序与查找", "快速排序", "散列表"],
    "存储系统": ["数据表示", "存储系统", "Cache映射", "存储层次"],
    "指令系统": ["数据表示", "指令系统", "寻址方式", "CPU结构"],
    "CPU结构": ["指令系统", "CPU结构", "流水线", "控制器"],
  };

  if (pathMap[pointName]) return pathMap[pointName];
  if (subject === "计算机网络") return ["网络体系结构", "传输层", pointName, "典型协议应用"];
  if (subject === "操作系统") return ["进程管理", pointName, "典型题型", "错因复盘"];
  if (subject === "数据结构") return ["线性结构", pointName, "算法应用", "复杂度分析"];
  if (subject === "计算机组成原理") return ["数据表示", pointName, "硬件执行过程", "综合题训练"];
  return ["核心概念", pointName, "关联知识", "练习巩固"];
}

function inferKnowledgePoints(text: string, subject: string): KnowledgeDiagnosis[] {
  const matched = knowledgeRules
    .filter((rule) => rule.subject === subject || includesAny(text, rule.keywords))
    .filter((rule) => includesAny(text, rule.keywords))
    .slice(0, 4)
    .map((rule, index) => ({
      name: rule.name,
      subject: rule.subject,
      level: index === 0 ? "review" as const : index === 1 ? "weak" as const : "mastered" as const,
      reason: index === 1 ? "该知识点通常需要结合题目继续巩固。" : "本次问题中出现了直接关联信号。",
    }));

  if (matched.length > 0) return matched;
  return [{
    name: subject === "408 综合知识" ? "核心概念识别" : subject,
    subject,
    level: "review",
    reason: "当前问题需要先确认概念边界，再进入例题训练。",
  }];
}

function compactSnippet(text: string, maxLength = 96) {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, maxLength)}...`;
}

function stepText(step: AgentStep) {
  const output = typeof step.output_data === "string" ? step.output_data : "";
  const input = typeof step.input_data === "string" ? step.input_data : "";
  return output || input || JSON.stringify(step).slice(0, 180);
}

function buildEvidenceItems(sources: string[], agentSteps: AgentStep[], answer: string) {
  const stepEvidence = agentSteps
    .filter((step) => step.tool_name || step.output_data || step.sources)
    .slice(0, 3)
    .map((step, index) => {
      const toolName = typeof step.tool_name === "string" ? step.tool_name : "retrieve_evidence";
      return {
        title: toolLabels[toolName] || toolName,
        snippet: compactSnippet(stepText(step)),
        score: Math.max(72, 92 - index * 7),
        reason: "该证据来自 Agent 工具调用结果，用于约束回答内容。",
      };
    });

  if (stepEvidence.length > 0) return stepEvidence;

  if (sources.length > 0) {
    return sources.slice(0, 3).map((source, index) => ({
      title: source,
      snippet: compactSnippet(answer, 88),
      score: Math.max(70, 88 - index * 6),
      reason: "该来源被系统标记为本次回答的参考依据。",
    }));
  }

  return [{
    title: "知识库检索结果",
    snippet: compactSnippet(answer, 88),
    score: 64,
    reason: "当前消息未返回明确来源，展示回答文本中的可解释依据。",
  }];
}

function buildTeachingTrace(props: TeachingAnalysisPanelProps): TeachingTrace {
  const query = props.query || "";
  const analysisText = `${query}\n${props.answer}`;
  const intent = inferIntent(analysisText);
  const subject = inferSubject(analysisText);
  const knowledgePoints = inferKnowledgePoints(analysisText, subject);
  const mainKnowledgePoint = knowledgePoints[0]?.name || subject;
  const difficulty = inferDifficulty(analysisText, knowledgePoints.length);
  const strategy = inferStrategy(intent, difficulty);
  const sources = props.sources || [];
  const agentSteps = props.agentSteps || [];
  const agentLabel = props.agentName ? agentLabels[props.agentName] || props.agentName : "智能问答 Agent";

  return {
    intent,
    subject,
    difficulty,
    strategy,
    knowledgePoints,
    evidenceItems: buildEvidenceItems(sources, agentSteps, props.answer),
    learningPath: inferLearningPath(mainKnowledgePoint, subject),
    timeline: [
      { title: "问题解析", detail: `识别为${intent}任务，优先判断学科和考点。`, status: "done" },
      { title: "知识点定位", detail: `定位到${subject}，命中 ${knowledgePoints.map((point) => point.name).join("、")}。`, status: "done" },
      { title: "RAG 检索", detail: sources.length > 0 ? `命中 ${sources.length} 个参考来源。` : "未返回明确来源，使用回答内容做可解释展示。", status: "done" },
      { title: "Agent 协同", detail: `${agentLabel} 完成回答生成与结果治理。`, status: "done" },
      { title: "学习建议", detail: strategy, status: "active" },
    ],
  };
}

function levelStyle(level: DiagnosisLevel) {
  if (level === "weak") return { label: "薄弱", className: "border-rose-200 bg-rose-50 text-rose-700" };
  if (level === "review") return { label: "需巩固", className: "border-amber-200 bg-amber-50 text-amber-700" };
  return { label: "已掌握", className: "border-emerald-200 bg-emerald-50 text-emerald-700" };
}

function TeachingAnalysisPanelComponent(props: TeachingAnalysisPanelProps) {
  const { answer, agentName, agentSteps, governance, query, sources } = props;
  const trace = useMemo(
    () => buildTeachingTrace({ answer, agentName, agentSteps, governance, query, sources }),
    [answer, agentName, agentSteps, governance, query, sources],
  );
  const confidence = governance?.confidence || "unknown";
  const hasSource = governance?.has_source ?? (sources || []).length > 0;

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-slate-50/80 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-bold text-slate-950">智能教学分析</span>
          <span className="rounded-full bg-cyan-100 px-2 py-0.5 text-xs font-semibold text-cyan-700">{trace.subject}</span>
          <span className="rounded-full bg-slate-900 px-2 py-0.5 text-xs font-semibold text-white">{trace.difficulty}</span>
        </div>
        <div className="mt-2 grid gap-2 text-xs text-slate-600 sm:grid-cols-3">
          <div>问题类型：<span className="font-semibold text-slate-900">{trace.intent}</span></div>
          <div>证据状态：<span className="font-semibold text-slate-900">{hasSource ? "已命中来源" : "待补充来源"}</span></div>
          <div>治理置信度：<span className="font-semibold text-slate-900">{confidence}</span></div>
        </div>
      </div>

      <div className="grid gap-4 p-4 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-4">
          <section>
            <h4 className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">Teaching Trace</h4>
            <div className="mt-3 space-y-2">
              {trace.timeline.map((item, index) => (
                <div key={item.title} className="grid grid-cols-[28px_1fr] gap-3">
                  <div className="flex flex-col items-center">
                    <div className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold ${item.status === "active" ? "bg-slate-900 text-white" : "bg-cyan-500 text-white"}`}>
                      {index + 1}
                    </div>
                    {index < trace.timeline.length - 1 && <div className="mt-1 h-8 w-px bg-slate-200" />}
                  </div>
                  <div>
                    <div className="text-sm font-bold text-slate-950">{item.title}</div>
                    <div className="mt-0.5 text-xs leading-5 text-slate-500">{item.detail}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section>
            <h4 className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">RAG Evidence</h4>
            <div className="mt-3 space-y-2">
              {trace.evidenceItems.map((item) => (
                <div key={item.title} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <div className="flex items-center justify-between gap-3">
                    <div className="truncate text-sm font-bold text-slate-900">{item.title}</div>
                    <div className="shrink-0 text-xs font-semibold text-cyan-700">相似度 {item.score}%</div>
                  </div>
                  <p className="mt-1 text-xs leading-5 text-slate-500">{item.snippet}</p>
                  <p className="mt-1 text-xs text-slate-400">{item.reason}</p>
                </div>
              ))}
            </div>
          </section>
        </div>

        <div className="space-y-4">
          <section>
            <h4 className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">Knowledge Diagnosis</h4>
            <div className="mt-3 space-y-2">
              {trace.knowledgePoints.map((point) => {
                const style = levelStyle(point.level);
                return (
                  <div key={point.name} className="rounded-lg border border-slate-200 px-3 py-2">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-sm font-bold text-slate-950">{point.name}</div>
                      <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${style.className}`}>{style.label}</span>
                    </div>
                    <div className="mt-1 text-xs text-slate-400">{point.subject}</div>
                    <p className="mt-1 text-xs leading-5 text-slate-500">{point.reason}</p>
                    {props.onOpenKnowledgeGraph && (
                      <button
                        type="button"
                        onClick={() => props.onOpenKnowledgeGraph?.(point.name)}
                        className="mt-2 rounded-full bg-slate-900 px-3 py-1 text-xs font-semibold text-white transition hover:bg-slate-700"
                      >
                        查看图谱
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </section>

          <section className="rounded-lg bg-slate-950 px-3 py-3 text-white">
            <h4 className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">Learning Path</h4>
            <p className="mt-2 text-sm font-semibold leading-6">{trace.strategy}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {trace.learningPath.map((item, index) => (
                <span key={`${item}-${index}`} className="inline-flex items-center gap-2">
                  <span className={index === trace.learningPath.length - 1 ? "rounded-full bg-white px-2.5 py-1 text-xs font-bold text-slate-950" : "rounded-full bg-white/10 px-2.5 py-1 text-xs font-semibold text-slate-100"}>
                    {item}
                  </span>
                  {index < trace.learningPath.length - 1 && <span className="text-slate-500">→</span>}
                </span>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {props.onOpenKnowledgeGraph && (
                <button
                  type="button"
                  onClick={() => props.onOpenKnowledgeGraph?.(trace.knowledgePoints[0]?.name || trace.subject)}
                  className="rounded-full bg-cyan-400 px-3 py-1.5 text-xs font-bold text-slate-950 transition hover:bg-cyan-300"
                >
                  在知识图谱中查看路径
                </button>
              )}
              {props.onGenerateSimilarPractice && (
                <button
                  type="button"
                  onClick={() => props.onGenerateSimilarPractice?.(trace.knowledgePoints[0]?.name || trace.subject)}
                  className="rounded-full border border-white/15 px-3 py-1.5 text-xs font-semibold text-slate-100 transition hover:border-white/35 hover:bg-white/10"
                >
                  生成同类练习
                </button>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export const TeachingAnalysisPanel = memo(TeachingAnalysisPanelComponent);
