"use client";

import { useKnowledgeCollections } from "@/hooks/useKnowledgeCollections";
import { BuildTipsCard } from "./BuildTipsCard";
import { CollectionList } from "./CollectionList";
import { KnowledgeUploadCard } from "./KnowledgeUploadCard";

export default function KnowledgePanel() {
  const {
    collections,
    uploading,
    category,
    uploadResult,
    collectionsError,
    fileInputRef,
    setCategory,
    uploadFiles,
    deleteCollection,
  } = useKnowledgeCollections();

  return (
    <div className="mx-auto flex h-full max-w-6xl flex-col gap-6 overflow-y-auto p-6 text-slate-800">
      <div className="grid gap-6 lg:grid-cols-[1.3fr_0.9fr]">
        <KnowledgeUploadCard
          category={category}
          uploading={uploading}
          uploadResult={uploadResult}
          fileInputRef={fileInputRef}
          onCategoryChange={setCategory}
          onUpload={() => void uploadFiles()}
        />
        <BuildTipsCard />
      </div>
      <CollectionList
        collections={collections}
        error={collectionsError}
        onDelete={(name) => void deleteCollection(name)}
      />
    </div>
  );
}
