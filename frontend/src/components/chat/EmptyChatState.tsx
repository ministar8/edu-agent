import { memo } from "react";

import { chatSuggestions } from "./chatMeta";

type EmptyChatStateProps = {
  onSelectSuggestion: (suggestion: string) => void;
};

function EmptyChatStateComponent({ onSelectSuggestion }: EmptyChatStateProps) {
  return (
    <div className="flex min-h-full items-center justify-center px-4 py-12">
      <div className="w-full max-w-md rounded-[28px] border border-slate-200 bg-white px-8 py-10 text-center text-slate-500 shadow-[0_18px_50px_rgba(15,23,42,0.08)]">
        <div className="mb-4 text-6xl">🎓</div>
        <h3 className="text-xl font-semibold text-slate-800">智能教学辅导系统</h3>
        <p className="mt-2 text-sm text-slate-500">试试问我：</p>
        <div className="mt-6 space-y-2">
          {chatSuggestions.map((suggestion) => (
            <button
              key={suggestion}
              onClick={() => onSelectSuggestion(suggestion)}
              className="block w-full rounded-2xl border border-blue-100 bg-blue-50 px-4 py-2.5 text-sm text-blue-600 transition hover:bg-blue-100"
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
