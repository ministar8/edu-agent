export { knowledgeCategories as ragCollections } from "@/lib/collections";

export const stepIcons: Record<string, string> = {
  input: "📝",
  search: "🔍",
  results: "📊",
  output: "📋",
  error: "❌",
};

export const stepColors: Record<string, string> = {
  input: "border-emerald-400 bg-emerald-50",
  search: "border-green-400 bg-green-50",
  results: "border-stone-400 bg-stone-50",
  output: "border-blue-400 bg-blue-50",
  error: "border-red-400 bg-red-50",
};

export const stepDescriptions: Record<string, string> = {
  input: "用户输入的原始查询",
  search: "在向量数据库中检索相似文档",
  results: "检索到的相关文档及相似度分数",
  output: "最终构建的上下文",
  error: "检索过程出错",
};
