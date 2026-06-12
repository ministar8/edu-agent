export interface ConversationItem {
  id: number;
  thread_id: string;
  title: string;
  summary: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationDetail {
  id: number;
  thread_id: string;
  title: string;
  summary: string;
  created_at: string;
  updated_at: string;
  messages: ConversationMessage[];
}

export interface ConversationMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  agent_name: string | null;
  sources: string[];
  governance: Record<string, unknown> | null;
  parent_id: number | null;
  siblings_order: number;
  child_count: number;
  created_at: string;
}
