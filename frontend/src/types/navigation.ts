export type TabType = "chat" | "questions" | "agents" | "knowledge" | "rag" | "kgraph" | "tracking";

export type AppTab = {
  id: TabType;
  label: string;
  icon: (props: { size?: number; className?: string }) => React.ReactNode;
};
