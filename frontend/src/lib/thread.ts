/**
 * Extract the base thread ID from a potentially prefixed thread ID.
 * Backend may prefix thread IDs with a namespace like "conv:abc123".
 */
export function getBaseThreadId(threadId: string): string {
  return threadId.includes(":") ? threadId.split(":").slice(1).join(":") : threadId;
}

/** Generate a unique session thread ID for new conversations. */
export function generateThreadId(): string {
  return `session-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
