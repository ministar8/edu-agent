import { memo, RefObject, useState, useEffect } from "react";

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
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (uploading) {
      setStep(1);
      const interval = setInterval(() => {
        setStep((prev) => (prev < 4 ? prev + 1 : prev));
      }, 2500);
      return () => clearInterval(interval);
    } else {
      setStep(0);
    }
  }, [uploading]);

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
          {uploading ? "导入构建中..." : "上传并构建知识库"}
        </button>
        <span className="text-xs text-slate-400">支持 PDF / TXT / MD / DOCX，多文件批量导入</span>
      </div>

      {/* ETL Pipeline Stepper Progress */}
      {uploading && (
        <div className="mt-6 rounded-2xl border border-blue-100 bg-blue-50/20 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-blue-700 flex items-center gap-1.5 animate-pulse">
              <span className="inline-block h-2 w-2 rounded-full bg-blue-600" />
              后台自适应 ETL 流水线正在执行
            </span>
            <span className="text-[10px] text-blue-500">流式并发比对模式</span>
          </div>

          <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
            {[
              { id: 1, label: "内容读取解析", desc: "PDF/TXT格式化" },
              { id: 2, label: "语义切分去重", desc: "自适应块元对齐" },
              { id: 3, label: "向量化索引化", desc: "Chroma 向量入库" },
              { id: 4, label: "知识图谱挂载", desc: "Neo4j 边关系挖掘" },
            ].map((s) => {
              const isActive = step === s.id;
              const isCompleted = step > s.id;
              return (
                <div key={s.id} className={`rounded-xl p-3 border transition-colors ${
                  isActive ? "bg-blue-50/80 border-blue-200 text-blue-900" :
                  isCompleted ? "bg-emerald-50/50 border-emerald-100 text-emerald-800" :
                  "bg-slate-50/50 border-slate-100 text-slate-400"
                }`}>
                  <div className="flex items-center gap-1.5 mb-1 text-xs font-bold">
                    {isCompleted ? (
                      <svg className="h-4 w-4 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                      </svg>
                    ) : isActive ? (
                      <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
                    ) : (
                      <span className="inline-block h-4 w-4 rounded-full bg-slate-200 text-[9px] text-slate-500 text-center leading-4 font-bold">{s.id}</span>
                    )}
                    <span className="truncate">{s.label}</span>
                  </div>
                  <div className="text-[10px] opacity-75">{s.desc}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <UploadResultView result={uploadResult} />
    </section>
  );
}

export const KnowledgeUploadCard = memo(KnowledgeUploadCardComponent);
