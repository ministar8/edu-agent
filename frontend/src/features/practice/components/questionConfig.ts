import type { Difficulty } from "@/shared/types/question";

export const difficultyOptions: { value: Difficulty; label: string }[] = [
  { value: "mixed", label: "混合难度" },
  { value: "basic", label: "基础" },
  { value: "medium", label: "中等" },
  { value: "hard", label: "困难" },
];

export const topicSuggestions = [
  "数据结构-二叉树",
  "数据结构-图论",
  "计算机组成原理-CPU",
  "计算机组成原理-存储器",
  "操作系统-进程管理",
  "操作系统-死锁",
  "计算机网络-传输层",
  "计算机网络-数据链路层",
];
