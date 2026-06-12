export interface Governance {
  confidence: string;
  has_source: boolean;
  passed: boolean;
  flags: string[];
}

export interface AgentStep {
  agent_name?: string;
  action?: string;
  tool_name?: string;
  input_data?: string;
  output_data?: string;
  sources?: string[];
  timestamp?: number;
  [key: string]: unknown;
}

export interface Message {
  id?: number;
  role: "user" | "assistant";
  content: string;
  agentName?: string;
  sources?: string[];
  agentSteps?: AgentStep[];
  governance?: Governance;
  parentId: number | null;
  siblingsOrder: number;
  childCount: number;
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
  activeLeafId: number | null;
};
