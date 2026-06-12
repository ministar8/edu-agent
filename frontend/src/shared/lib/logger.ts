/**
 * Structured logging utility for consistent terminal output.
 * Prefixes all messages with [Module] for easy filtering.
 */

type LogLevel = "info" | "warn" | "error";

function formatMessage(level: LogLevel, module: string, message: string): string {
  return `[${module}] ${level.toUpperCase()}: ${message}`;
}

export const log = {
  info: (module: string, message: string, ...args: unknown[]) => {
    console.info(formatMessage("info", module, message), ...args);
  },
  warn: (module: string, message: string, ...args: unknown[]) => {
    console.warn(formatMessage("warn", module, message), ...args);
  },
  error: (module: string, message: string, ...args: unknown[]) => {
    console.error(formatMessage("error", module, message), ...args);
  },
};
