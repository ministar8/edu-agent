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
  baseThreadId: string;
  conversationId: number | null;
};

export type ChatPanelProps = {
  state: ChatPanelState;
  setState: React.Dispatch<React.SetStateAction<ChatPanelState>>;
};
