"use client";

import { useState, useEffect, useRef } from "react";
import axios from "axios";

import { API_BASE_URL } from "@/lib/api";

interface Collection {
  name: string;
  count: number;
}

interface UploadResultItem {
  filename: string;
  chunk_count: number;
  success: boolean;
  error?: string;
}

interface UploadResult {
  results?: UploadResultItem[];
  error?: string;
}

export default function KnowledgePanel() {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [uploading, setUploading] = useState(false);
  const [category, setCategory] = useState("general");
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchCollections();
  }, []);

  const fetchCollections = async () => {
    try {
      const res = await axios.get(`${API_BASE_URL}/api/knowledge/collections`);
      setCollections(res.data.collections);
    } catch {
      setCollections([]);
    }
  };

  const handleUpload = async () => {
    const files = fileInputRef.current?.files;
    if (!files || files.length === 0) return;

    setUploading(true);
    setUploadResult(null);

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append("files", files[i]);
    }
    formData.append("category", category);

    try {
      const res = await axios.post(`${API_BASE_URL}/api/knowledge/batch-upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setUploadResult(res.data);
      fetchCollections();
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : String(error);
      setUploadResult({ error: msg });
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (name: string) => {
    if (!confirm(`确定删除知识库 "${name}" 吗？`)) return;
    try {
      await axios.delete(`/api/knowledge/collections/${name}`);
      fetchCollections();
    } catch {}
  };

  const categories = [
    { value: "general", label: "通用教材" },
    { value: "questions", label: "题库" },
    { value: "answers", label: "标准答案" },
    { value: "learning_paths", label: "学习路径" },
  ];

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h2 className="text-xl font-bold text-gray-800 mb-4">知识库管理</h2>
      <p className="text-sm text-gray-500 mb-6">
        上传教材、题库、标准答案等文档，系统将自动解析、切分、向量化并存入知识库
      </p>

      {/* Upload Section */}
      <div className="bg-white rounded-xl border p-6 mb-6">
        <h3 className="font-semibold text-gray-700 mb-4">上传文档</h3>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm text-gray-600 mb-1">知识库类型</label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm"
            >
              {categories.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">选择文件</label>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.txt,.md,.docx"
              className="w-full border rounded-lg px-3 py-2 text-sm"
            />
          </div>
        </div>

        <button
          onClick={handleUpload}
          disabled={uploading}
          className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm"
        >
          {uploading ? "上传处理中..." : "上传并构建知识库"}
        </button>

        {uploadResult && (
          <div className="mt-4 p-3 bg-gray-50 rounded-lg text-sm">
            {uploadResult.results ? (
              <div>
                <p className="font-medium text-green-600">上传成功！</p>
                {uploadResult.results.map((r, i) => (
                  <p key={i} className="text-gray-600">
                    {r.filename}: {r.chunk_count} 个文本块
                  </p>
                ))}
              </div>
            ) : (
              <p className="text-red-600">上传失败: {uploadResult.error}</p>
            )}
          </div>
        )}
      </div>

      {/* Collections Section */}
      <div className="bg-white rounded-xl border p-6">
        <h3 className="font-semibold text-gray-700 mb-4">已有知识库</h3>
        {collections.length === 0 ? (
          <p className="text-gray-400 text-sm">暂无知识库，请先上传文档</p>
        ) : (
          <div className="space-y-3">
            {collections.map((col) => (
              <div
                key={col.name}
                className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
              >
                <div>
                  <span className="font-medium text-gray-700">{col.name}</span>
                  <span className="ml-2 text-sm text-gray-400">
                    {col.count} 条记录
                  </span>
                </div>
                <button
                  onClick={() => handleDelete(col.name)}
                  className="text-red-500 hover:text-red-700 text-sm"
                >
                  删除
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
