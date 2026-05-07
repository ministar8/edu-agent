import { memo } from "react";

import type { Collection } from "@/types/knowledge";

type CollectionListProps = {
  collections: Collection[];
  error: string;
  onDelete: (name: string) => void;
};

function CollectionListComponent({ collections, error, onDelete }: CollectionListProps) {
  return (
    <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-5 flex items-center justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-slate-900">已有知识库</h3>
          <p className="mt-1 text-sm text-slate-500">查看当前各集合的索引记录，并按需删除重建。</p>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
          {collections.length} 个集合
        </span>
      </div>

      {collections.length === 0 ? (
        <div className="rounded-3xl bg-slate-50 px-6 py-12 text-center text-sm text-slate-400">
          {error || "暂无知识库，请先上传文档开始构建。"}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {collections.map((collection) => (
            <div
              key={collection.name}
              className="rounded-3xl border border-slate-200 bg-slate-50 p-5 transition hover:border-slate-300 hover:bg-white"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-base font-medium text-slate-800">{collection.name}</div>
                  <div className="mt-2 text-sm text-slate-500">{collection.count} 条索引记录</div>
                </div>
                <button
                  onClick={() => onDelete(collection.name)}
                  className="rounded-xl px-3 py-1.5 text-sm text-red-500 transition hover:bg-red-50 hover:text-red-600"
                >
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export const CollectionList = memo(CollectionListComponent);
