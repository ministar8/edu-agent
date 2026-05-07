export { knowledgeCategories as ragCollections } from "@/lib/collections";

export const stepIcons: Record<string, string> = {
  input: "📝",
  transform: "🔄",
  search: "🔍",
  results: "📊",
};

export const stepColors: Record<string, string> = {
  input: "border-blue-400 bg-blue-50",
  transform: "border-yellow-400 bg-yellow-50",
  search: "border-green-400 bg-green-50",
  results: "border-purple-400 bg-purple-50",
};

export const stepDescriptions: Record<string, string> = {
  input: "用户输入的原始查询",
  transform: "查询归一化与同义词扩展",
  search: "在向量数据库中检索相似文档",
  results: "检索到的相关文档及相似度分数",
};
