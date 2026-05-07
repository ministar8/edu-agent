import { memo } from "react";

type ChatInputProps = {
  input: string;
  loading: boolean;
  onInputChange: (value: string) => void;
  onSubmit: () => void;
};

function ChatInputComponent({ input, loading, onInputChange, onSubmit }: ChatInputProps) {
  return (
    <div className="bg-[#fbfcfe] px-6 pb-6 pt-4">
      <div className="mx-auto max-w-5xl rounded-full border border-slate-200 bg-white px-5 py-3 shadow-[0_10px_24px_rgba(15,23,42,0.08)]">
        <div className="flex items-center gap-3">
          <input
            type="text"
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                onSubmit();
              }
            }}
            placeholder="有问题，尽管问"
            className="flex-1 bg-transparent px-1 text-[15px] text-slate-700 outline-none placeholder:text-slate-400"
            disabled={loading}
          />
          <button
            onClick={onSubmit}
            disabled={loading || !input.trim()}
            className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-slate-950 text-white shadow-sm transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
            aria-label="发送消息"
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              className="h-6 w-6"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 19V5" />
              <path d="M5 12l7-7 7 7" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

export const ChatInput = memo(ChatInputComponent);
