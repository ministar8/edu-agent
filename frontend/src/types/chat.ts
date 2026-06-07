export interface Governance {
  confidence: string;
  has_source: boolean;
  passed: boolean;
  flags: string[];
}

export interface Message {
  role: "user" | "assistant";
  content: string;
  agentName?: string;
  sources?: string[];
  governance?: Governance;
  timestamp: Date;
}

export type ChatPanelState = {
  messages: Message[];
  input: string;
  loading: boolean;
  streamingText: string;
  streamingAgent: string;
  activeTool: string | null;
  streamingGovernance: Governance | null;
  statusLabel: string;
  baseThreadId: string;
  conversationId: number | null;
};
