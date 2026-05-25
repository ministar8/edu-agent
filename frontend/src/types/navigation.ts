import type React from "react";

export type TabType = "chat" | "questions" | "agents" | "knowledge" | "rag" | "kgraph" | "tracking";

export type AppTab = {
  id: TabType;
  label: string;
  icon: React.FC<{ size?: number; className?: string }>;
};
