"use client";

import { useRagProcess } from "@/hooks/useRagProcess";
import { RagSearchCard } from "./RagSearchCard";
import { RagStepList } from "./RagStepList";

export default function RAGProcessPanel() {
  const {
    query,
    collection,
    steps,
    loading,
    activeStep,
    setQuery,
    setCollection,
    searchRAG,
  } = useRagProcess();

  return (
    <div className="mx-auto flex h-full max-w-6xl flex-col gap-6 overflow-y-auto p-6 text-slate-800">
      <RagSearchCard
        query={query}
        collection={collection}
        loading={loading}
        onQueryChange={setQuery}
        onCollectionChange={setCollection}
        onSearch={() => void searchRAG()}
      />
      <RagStepList steps={steps} loading={loading} activeStep={activeStep} />
    </div>
  );
}
