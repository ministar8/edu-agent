import { memo } from "react";

function SourceListComponent({ sources }: { sources: string[] }) {
  if (sources.length === 0) {
    return null;
  }

  return (
    <div className="mt-2 pt-2 border-t border-slate-200">
      <div className="text-xs text-slate-400">参考来源：</div>
      {sources.map((src, index) => (
        <span
          key={`${src}-${index}`}
          className="inline-block text-xs bg-blue-100 text-blue-600 px-2 py-0.5 rounded mr-1 mt-1"
        >
          {src}
        </span>
      ))}
    </div>
  );
}

export const SourceList = memo(SourceListComponent);
