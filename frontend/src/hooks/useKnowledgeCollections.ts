import { useCallback, useEffect, useRef, useState } from "react";

import { getErrorMessage } from "@/lib/errors";
import { http } from "@/lib/http";
import type { Collection, UploadResult } from "@/types/knowledge";

export function useKnowledgeCollections() {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [uploading, setUploading] = useState(false);
  const [category, setCategory] = useState("data_structure");
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [collectionsError, setCollectionsError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchCollections = useCallback(async () => {
    try {
      const res = await http.get("/api/knowledge/collections");
      setCollections(res.data.collections);
      setCollectionsError("");
    } catch (error: unknown) {
      setCollections([]);
      setCollectionsError(getErrorMessage(error, "知识库列表加载失败"));
    }
  }, []);

  useEffect(() => {
    void fetchCollections();
  }, [fetchCollections]);

  const uploadFiles = useCallback(async () => {
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
      const res = await http.post("/api/knowledge/batch-upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setUploadResult(res.data);
      void fetchCollections();
    } catch (error: unknown) {
      setUploadResult({ error: getErrorMessage(error, "上传失败") });
    } finally {
      setUploading(false);
    }
  }, [category, fetchCollections]);

  const deleteCollection = useCallback(async (name: string) => {
    if (!confirm(`确定删除知识库 "${name}" 吗？`)) return;

    try {
      await http.delete(`/api/knowledge/collections/${name}`);
      void fetchCollections();
    } catch (error: unknown) {
      setCollectionsError(getErrorMessage(error, "删除知识库失败"));
    }
  }, [fetchCollections]);

  return {
    collections,
    uploading,
    category,
    uploadResult,
    collectionsError,
    fileInputRef,
    setCategory,
    uploadFiles,
    deleteCollection,
  };
}
