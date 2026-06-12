export type TabType = "dashboard" | "chat" | "practice" | "kgraph" | "debug";

export type AppTab = {
  id: TabType;
  label: string;
  icon: (props: { size?: number; className?: string }) => React.ReactNode;
};
