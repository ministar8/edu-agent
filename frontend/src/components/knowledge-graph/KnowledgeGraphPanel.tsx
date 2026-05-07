"use client";

import { useKnowledgeGraph } from "@/hooks/useKnowledgeGraph";
import { ImportDemoGraphPanel } from "./ImportDemoGraphPanel";
import { KnowledgeGraphCanvas } from "./KnowledgeGraphCanvas";
import { KnowledgeGraphToolbar } from "./KnowledgeGraphToolbar";

export default function KnowledgeGraphPanel() {
  const {
    nodes,
    edges,
    showImport,
    error,
    setShowImport,
    fetchGraph,
    importDemoData,
  } = useKnowledgeGraph();

  return (
    <div className="flex flex-col h-full">
      <KnowledgeGraphToolbar
        showImport={showImport}
        onRefresh={() => void fetchGraph()}
        onToggleImport={() => setShowImport(!showImport)}
      />
      {showImport && (
        <ImportDemoGraphPanel
          onImport={() => void importDemoData()}
          onCancel={() => setShowImport(false)}
        />
      )}
      <KnowledgeGraphCanvas nodes={nodes} edges={edges} error={error} />
    </div>
  );
}
