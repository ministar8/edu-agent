import { AgentFlow } from "@/features/agent-flow";
import { ChatPanel } from "@/features/chat";
import { KnowledgePanel } from "@/features/knowledge-base";
import { KnowledgeGraphPanel } from "@/features/knowledge-map";
import { QuestionPanel } from "@/features/practice";
import { RAGProcessPanel } from "@/features/rag-process";
import { TrackingPanel } from "@/features/tracking";
import type { ChatPanelState } from "@/shared/types/chat";
import type { TabType } from "@/shared/types/navigation";
import type { QuestionPanelState } from "@/shared/types/question";

type WorkspaceContentProps = {
  activeTab: TabType;
  chatState: ChatPanelState;
  setChatState: React.Dispatch<React.SetStateAction<ChatPanelState>>;
  questionState: QuestionPanelState;
  setQuestionState: React.Dispatch<React.SetStateAction<QuestionPanelState>>;
  knowledgeGraphFocus: string;
  onOpenKnowledgeGraph: (focus: string) => void;
  onGenerateSimilarPractice: (topic: string) => void;
  onJumpToChat: (question: string) => void;
};

export function WorkspaceContent({
  activeTab,
  chatState,
  setChatState,
  questionState,
  setQuestionState,
  knowledgeGraphFocus,
  onOpenKnowledgeGraph,
  onGenerateSimilarPractice,
  onJumpToChat,
}: WorkspaceContentProps) {
  return (
    <main className="min-h-0 flex-1 overflow-hidden bg-stone-50">
      {activeTab === "chat" && (
        <ChatPanel
          state={chatState}
          setState={setChatState}
          onOpenKnowledgeGraph={onOpenKnowledgeGraph}
          onGenerateSimilarPractice={onGenerateSimilarPractice}
        />
      )}
      {activeTab === "questions" && <QuestionPanel state={questionState} setState={setQuestionState} />}
      {activeTab === "agents" && <AgentFlow />}
      {activeTab === "knowledge" && <KnowledgePanel />}
      {activeTab === "rag" && <RAGProcessPanel />}
      {activeTab === "kgraph" && (
        <KnowledgeGraphPanel
          focusLabel={knowledgeGraphFocus}
          onJumpToChat={onJumpToChat}
          onJumpToQuestions={onGenerateSimilarPractice}
        />
      )}
      {activeTab === "tracking" && <TrackingPanel onGenerateSimilarPractice={onGenerateSimilarPractice} />}
    </main>
  );
}
