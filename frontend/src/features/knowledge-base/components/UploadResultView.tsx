import { memo } from "react";

import type { UploadResult } from "@/shared/types/knowledge";

type UploadResultViewProps = {
  result: UploadResult | null;
};

function UploadResultViewComponent({ result }: UploadResultViewProps) {
  if (!result) {
    return null;
  }

  return (
    <div className="mt-6 rounded-3xl border border-slate-200 bg-slate-50 p-4 text-sm">
      {result.results ? (
        <div>
          <p className="font-medium text-emerald-700">上传成功，已完成索引构建</p>
          <div className="mt-3 space-y-2">
            {result.results.map((item, index) => (
              <div key={`${item.filename}-${index}`} className="rounded-2xl bg-white px-4 py-3 text-slate-600 shadow-sm">
                {item.filename}: {item.chunk_count} 个文本块{item.graph_nodes > 0 ? `，图谱 ${item.graph_nodes} 节点 ${item.graph_edges} 边` : ""}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <p className="font-medium text-red-600">上传失败: {result.error}</p>
      )}
    </div>
  );
}

export const UploadResultView = memo(UploadResultViewComponent);
