export { knowledgeCategories as ragCollections } from "@/lib/collections";

export const stepIcons: Record<string, string> = {
  input: "📝",
  transform: "🔄",
  search: "🔍",
  results: "📊",
};

export const stepColors: Record<string, string> = {
  input: "border-emerald-400 bg-emerald-50",
  transform: "border-yellow-400 bg-yellow-50",
  search: "border-green-400 bg-green-50",
  results: "border-stone-400 bg-stone-50",
};

export const stepDescriptions: Record<string, string> = {
  input: "用户输入的原始查询",
  transform: "查询归一化与同义词扩展",
  search: "在向量数据库中检索相似文档",
  results: "检索到的相关文档及相似度分数",
};
