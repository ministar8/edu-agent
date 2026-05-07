import type { AppTab, TabType } from "@/types/navigation";

export const tabs: AppTab[] = [
  { id: "chat", label: "智能问答", icon: "💬" },
  { id: "questions", label: "题目生成", icon: "📝" },
  { id: "agents", label: "Agent协作", icon: "🤖" },
  { id: "knowledge", label: "知识库管理", icon: "📚" },
  { id: "rag", label: "RAG过程", icon: "🔍" },
  { id: "kgraph", label: "知识图谱", icon: "🕸️" },
];

export const roleLabels: Record<string, string> = {
  student: "学生",
  teacher: "教师",
  admin: "管理员",
};

export const tabDescriptions: Record<TabType, string> = {
  chat: "多 Agent 协同教学问答",
  questions: "练习题与测试内容生成",
  agents: "查看调度与协作过程",
  knowledge: "维护上传与索引构建",
  rag: "观察检索与重排流程",
  kgraph: "浏览知识点关系网络",
};
