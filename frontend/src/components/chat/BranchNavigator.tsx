import { memo } from "react";

type BranchNavigatorProps = {
  currentIndex: number;
  totalCount: number;
  onPrev: () => void;
  onNext: () => void;
};

function BranchNavigatorComponent({ currentIndex, totalCount, onPrev, onNext }: BranchNavigatorProps) {
  return (
    <div className="mt-1.5 inline-flex items-center gap-0.5 rounded-lg border border-slate-200 bg-white px-1 py-0.5 text-xs text-slate-500">
      <button
        onClick={onPrev}
        disabled={currentIndex <= 0}
        className="rounded px-1 py-0.5 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-30"
        aria-label="上一个分支"
      >
        <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>
      <span className="min-w-[2.5rem] text-center tabular-nums">
        {currentIndex + 1}/{totalCount}
      </span>
      <button
        onClick={onNext}
        disabled={currentIndex >= totalCount - 1}
        className="rounded px-1 py-0.5 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-30"
        aria-label="下一个分支"
      >
        <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </button>
    </div>
  );
}

export const BranchNavigator = memo(BranchNavigatorComponent);
