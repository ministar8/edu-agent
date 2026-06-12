import type { AppTab, TabType } from "@/shared/types/navigation";
import { IconChat, IconQuiz, IconAgents, IconGraph, IconDashboard } from "@/shared/ui/icons";

export const primaryTabs: AppTab[] = [
  { id: "dashboard", label: "学习工作台", icon: IconDashboard },
  { id: "chat", label: "智能问答", icon: IconChat },
  { id: "practice", label: "练习与错题", icon: IconQuiz },
  { id: "kgraph", label: "知识地图", icon: IconGraph },
];

export const utilityTabs: AppTab[] = [
  { id: "debug", label: "管理调试", icon: IconAgents },
];

export const tabs: AppTab[] = [...primaryTabs, ...utilityTabs];

export const roleLabels: Record<string, string> = {
  student: "学生",
  teacher: "教师",
  admin: "管理员",
};

export const tabDescriptions: Record<TabType, string> = {
  dashboard: "今日建议、薄弱点与下一步行动",
  chat: "多 Agent 协同教学问答",
  practice: "专项练习、批改反馈与错题复练",
  kgraph: "知识结构、前置依赖与学习入口",
  debug: "知识库、Agent 与 RAG 技术视图",
};
