export type TabType = "chat" | "questions" | "agents" | "knowledge" | "rag" | "kgraph";

export type AppTab = {
  id: TabType;
  label: string;
  icon: string;
};
