import { memo } from "react";
import { IconGraduation } from "@/shared/ui/icons";
import { chatSuggestions } from "./chatMeta";

type EmptyChatStateProps = { onSelectSuggestion: (suggestion: string) => void };

function EmptyChatStateComponent({ onSelectSuggestion }: EmptyChatStateProps) {
  return (
    <div className="flex min-h-full items-center justify-center px-4 py-16">
      <div className="w-full max-w-md text-center">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-600 text-white shadow-sm">
          <IconGraduation size={28} />
        </div>
        <h3 className="text-xl font-semibold text-slate-800">智能教学辅导</h3>
        <p className="mt-1.5 text-sm text-slate-400">Multi-Agent Tutoring System</p>
        <div className="mt-8 space-y-2">
          <p className="text-xs font-medium uppercase tracking-wider text-slate-400">试试问我</p>
          {chatSuggestions.map((suggestion) => (
            <button
              key={suggestion}
              onClick={() => onSelectSuggestion(suggestion)}
              className="block w-full rounded-xl border border-stone-200/80 bg-white px-4 py-3 text-left text-[13px] text-stone-600 shadow-sm transition hover:border-emerald-200 hover:bg-emerald-50/50 hover:text-emerald-700"
            >
              {suggestion}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export const EmptyChatState = memo(EmptyChatStateComponent);
