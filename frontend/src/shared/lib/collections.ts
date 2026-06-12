import type { KnowledgeCategory } from "@/shared/types/knowledge";

export const knowledgeCategories: KnowledgeCategory[] = [
  { value: "data_structure", label: "数据结构" },
  { value: "computer_organization", label: "计算机组成原理" },
  { value: "operating_system", label: "操作系统" },
  { value: "computer_network", label: "计算机网络" },
  { value: "questions", label: "题库" },
];

/** 学科 key → 中文标签映射（含追踪 API 返回的额外分类） */
export const CATEGORY_LABELS: Record<string, string> = {
  ...Object.fromEntries(knowledgeCategories.map((c) => [c.value, c.label])),
  learning_paths: "学习路径",
  answers: "标准答案",
};
