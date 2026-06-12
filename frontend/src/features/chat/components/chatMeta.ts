export const agentColors: Record<string, string> = {
  knowledge_agent: "bg-green-50 border-green-200",
  question_agent: "bg-pink-50 border-pink-200",
  grading_agent: "bg-emerald-50 border-emerald-200",
  path_agent: "bg-amber-50 border-amber-200",
  supervisor: "bg-stone-100 border-stone-300",
};

export const agentLabels: Record<string, string> = {
  knowledge_agent: "知识点检索Agent",
  question_agent: "题目生成Agent",
  grading_agent: "批改评估Agent",
  path_agent: "学习路径推荐Agent",
  supervisor: "Supervisor调度",
};

export const toolLabels: Record<string, string> = {
  knowledge_search: "检索知识库",
  text_search: "文本检索",
  kg_search: "图谱检索",
  search_question_templates: "检索题库",
  search_standard_answer: "检索标准答案",
  search_learning_path: "检索学习路径",
  query_knowledge_graph: "查询知识图谱",
};

export const chatSuggestions = [
  "什么是进程死锁？产生条件有哪些？",
  "给我出3道数据结构二叉树题目",
  "TCP和UDP的区别是什么？",
  "我该怎么复习计算机组成原理？",
];
