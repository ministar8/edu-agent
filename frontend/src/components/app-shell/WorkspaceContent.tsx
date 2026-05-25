import AgentFlow from "@/components/AgentFlow";
import ChatPanel from "@/components/chat/ChatPanel";
import KnowledgeGraphPanel from "@/components/knowledge-graph/KnowledgeGraphPanel";
import KnowledgePanel from "@/components/knowledge/KnowledgePanel";
import QuestionPanel from "@/components/questions/QuestionPanel";
import RAGProcessPanel from "@/components/rag/RAGProcessPanel";
import TrackingPanel from "@/components/tracking/TrackingPanel";
import type { ChatPanelState } from "@/types/chat";
import type { TabType } from "@/types/navigation";
import type { QuestionPanelState } from "@/types/question";

type WorkspaceContentProps = {
  activeTab: TabType;
  chatState: ChatPanelState;
  setChatState: React.Dispatch<React.SetStateAction<ChatPanelState>>;
  questionState: QuestionPanelState;
  setQuestionState: React.Dispatch<React.SetStateAction<QuestionPanelState>>;
};

export function WorkspaceContent({
  activeTab,
  chatState,
  setChatState,
  questionState,
  setQuestionState,
}: WorkspaceContentProps) {
  return (
    <main className="min-h-0 flex-1 overflow-hidden bg-stone-50">
      {activeTab === "chat" && <ChatPanel state={chatState} setState={setChatState} />}
      {activeTab === "questions" && <QuestionPanel state={questionState} setState={setQuestionState} />}
      {activeTab === "agents" && <AgentFlow />}
      {activeTab === "knowledge" && <KnowledgePanel />}
      {activeTab === "rag" && <RAGProcessPanel />}
      {activeTab === "kgraph" && <KnowledgeGraphPanel />}
      {activeTab === "tracking" && <TrackingPanel />}
    </main>
  );
}
