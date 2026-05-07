import { memo, RefObject } from "react";

import type { UploadResult } from "@/types/knowledge";
import { knowledgeCategories } from "./knowledgeConfig";
import { UploadResultView } from "./UploadResultView";

type KnowledgeUploadCardProps = {
  category: string;
  uploading: boolean;
  uploadResult: UploadResult | null;
  fileInputRef: RefObject<HTMLInputElement>;
  onCategoryChange: (category: string) => void;
  onUpload: () => void;
};

function KnowledgeUploadCardComponent({
  category,
  uploading,
  uploadResult,
  fileInputRef,
  onCategoryChange,
  onUpload,
}: KnowledgeUploadCardProps) {
  return (
    <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-xl font-semibold text-slate-900">文档入库与索引构建</h3>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            上传教材、题库、标准答案等文件，系统会自动完成清洗、切分、向量化、去重与知识图谱构建。
          </p>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
          ETL Pipeline
        </span>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">知识库类型</label>
          <select
            value={category}
            onChange={(event) => onCategoryChange(event.target.value)}
            className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition focus:border-slate-400 focus:ring-4 focus:ring-slate-200/70"
          >
            {knowledgeCategories.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">选择文件</label>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.txt,.md,.docx"
            className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none file:mr-3 file:rounded-xl file:border-0 file:bg-white file:px-3 file:py-1.5 file:text-sm file:text-slate-600"
          />
        </div>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <button
          onClick={onUpload}
          disabled={uploading}
          className="rounded-2xl bg-slate-800 px-5 py-3 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {uploading ? "上传处理中..." : "上传并构建知识库"}
        </button>
        <span className="text-xs text-slate-400">支持 PDF / TXT / MD / DOCX，多文件批量导入</span>
      </div>

      <UploadResultView result={uploadResult} />
    </section>
  );
}

export const KnowledgeUploadCard = memo(KnowledgeUploadCardComponent);
