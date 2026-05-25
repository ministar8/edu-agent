import { memo } from "react";

type ChatInputProps = {
  input: string;
  loading: boolean;
  onInputChange: (value: string) => void;
  onSubmit: () => void;
};

function ChatInputComponent({ input, loading, onInputChange, onSubmit }: ChatInputProps) {
  return (
    <div className="border-t border-stone-100 bg-white/80 px-6 pb-5 pt-4 backdrop-blur-sm">
      <div className="mx-auto max-w-3xl rounded-2xl border border-stone-200/80 bg-white px-4 py-2.5 shadow-sm transition-shadow focus-within:shadow-md focus-within:border-emerald-300">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                if (loading) return;
                onSubmit();
              }
            }}
            placeholder="输入你的问题..."
            className="flex-1 bg-transparent px-2 py-1.5 text-[14px] text-slate-700 outline-none placeholder:text-slate-400"
          />
          <button
            onClick={onSubmit}
            disabled={loading || !input.trim()}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-emerald-600 text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-stone-200 disabled:text-stone-400 disabled:shadow-none"
            aria-label="发送消息"
          >
            {loading ? (
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            ) : (
              <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 19V5" />
                <path d="M5 12l7-7 7 7" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export const ChatInput = memo(ChatInputComponent);
