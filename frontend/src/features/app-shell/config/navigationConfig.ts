import type { AppTab, TabType } from "@/shared/types/navigation";
import { IconChat, IconQuiz, IconAgents, IconLibrary, IconSearch, IconGraph, IconDashboard } from "@/shared/ui/icons";

export const tabs: AppTab[] = [
  { id: "chat", label: "智能问答", icon: IconChat },
  { id: "questions", label: "题目生成", icon: IconQuiz },
  { id: "agents", label: "Agent 协作", icon: IconAgents },
  { id: "knowledge", label: "知识库", icon: IconLibrary },
  { id: "rag", label: "RAG 过程", icon: IconSearch },
  { id: "kgraph", label: "知识图谱", icon: IconGraph },
  { id: "tracking", label: "学习仪表盘", icon: IconDashboard },
];

export const roleLabels: Record<string, string> = {
  student: "学生",
  teacher: "教师",
  admin: "管理员",
};

export const tabDescriptions: Record<TabType, string> = {
  chat: "多 Agent 协同教学问答",
  questions: "练习题目生成与评测",
  agents: "Agent 调度与协作流程",
  knowledge: "知识库上传与索引管理",
  rag: "检索增强生成过程追踪",
  kgraph: "知识点关系网络浏览",
  tracking: "知识掌握度与学习进度",
};
