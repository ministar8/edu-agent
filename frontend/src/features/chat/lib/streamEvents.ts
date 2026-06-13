import type { AgentStep, Governance } from "@/shared/types/chat";

export type ParsedStreamEvent = {
  eventType: string;
  data: Record<string, unknown>;
};

export type StreamParseState = {
  buffer: string;
  eventType: string;
};

export function toGovernance(data: Record<string, unknown>): Governance {
  return {
    confidence: typeof data.confidence === "string" ? data.confidence : "unknown",
    has_source: typeof data.has_source === "boolean" ? data.has_source : false,
    passed: typeof data.passed === "boolean" ? data.passed : true,
    flags: Array.isArray(data.flags) ? data.flags.filter((flag): flag is string => typeof flag === "string") : [],
  };
}

export function toAgentSteps(value: unknown): AgentStep[] {
  if (!Array.isArray(value)) return [];
  return value.filter((step): step is AgentStep => step !== null && typeof step === "object");
}

export function parseStreamEvents(state: StreamParseState, chunk: string) {
  const events: ParsedStreamEvent[] = [];
  const lines = (state.buffer + chunk).split("\n");
  let eventType = state.eventType;
  const buffer = lines.pop() || "";

  for (const line of lines) {
    if (line.startsWith("event: ")) {
      eventType = line.slice(7).trim();
      continue;
    }
    if (!line.startsWith("data: ")) continue;

    try {
      events.push({
        eventType,
        data: JSON.parse(line.slice(6)) as Record<string, unknown>,
      });
    } catch {
      continue;
    } finally {
      eventType = "";
    }
  }

  return { buffer, eventType, events };
}
