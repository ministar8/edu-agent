import { memo } from "react";

import { ragCollections } from "./ragConfig";

type RagSearchCardProps = {
  query: string;
  collection: string;
  loading: boolean;
  onQueryChange: (query: string) => void;
  onCollectionChange: (collection: string) => void;
  onSearch: () => void;
};

function RagSearchCardComponent({
  query,
  collection,
  loading,
  onQueryChange,
  onCollectionChange,
  onSearch,
}: RagSearchCardProps) {
  return (
    <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-xl font-semibold text-slate-900">RAG 检索过程可视化</h3>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            输入查询，观察从查询输入、多路召回、向量检索到结果排序的完整执行过程。
          </p>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
          Retrieval Pipeline
        </span>
      </div>

      <div className="grid gap-4 lg:grid-cols-[180px_1fr_120px]">
        <select
          value={collection}
          onChange={(event) => onCollectionChange(event.target.value)}
          className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition focus:border-slate-400 focus:ring-4 focus:ring-slate-200/70"
        >
          {ragCollections.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <input
          type="text"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && onSearch()}
          placeholder="输入检索查询，如：进程死锁的四个必要条件"
          maxLength={200}
          className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition focus:border-slate-400 focus:ring-4 focus:ring-slate-200/70"
        />
        <button
          onClick={onSearch}
          disabled={loading}
          className="rounded-2xl bg-slate-800 px-5 py-3 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "检索中..." : "检索"}
        </button>
      </div>
    </section>
  );
}

export const RagSearchCard = memo(RagSearchCardComponent);
