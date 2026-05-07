import { memo } from "react";
import { Background, Controls, Edge, MiniMap, Node, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { KnowledgeGraphEmptyState } from "./KnowledgeGraphEmptyState";

type KnowledgeGraphCanvasProps = {
  nodes: Node[];
  edges: Edge[];
  error: string;
};

function KnowledgeGraphCanvasComponent({ nodes, edges, error }: KnowledgeGraphCanvasProps) {
  return (
    <div className="flex-1">
      {nodes.length > 0 ? (
        <div style={{ height: "calc(100vh - 220px)" }}>
          <ReactFlow nodes={nodes} edges={edges} fitView>
            <Background color="#e2e8f0" gap={20} />
            <Controls />
            <MiniMap
              nodeStrokeColor="#667eea"
              nodeColor="#667eea"
              maskColor="rgba(102, 126, 234, 0.1)"
            />
          </ReactFlow>
        </div>
      ) : (
        <KnowledgeGraphEmptyState error={error} />
      )}
    </div>
  );
}

export const KnowledgeGraphCanvas = memo(KnowledgeGraphCanvasComponent);
