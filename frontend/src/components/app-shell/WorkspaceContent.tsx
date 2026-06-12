import ChatPanel from "@/components/chat/ChatPanel";
import StudyDashboardPanel from "@/components/dashboard/StudyDashboardPanel";
import DebugPanel from "@/components/debug/DebugPanel";
import KnowledgeGraphPanel from "@/components/knowledge-graph/KnowledgeGraphPanel";
import QuestionPanel from "@/components/questions/QuestionPanel";
import type { ChatPanelState } from "@/types/chat";
import type { TabType } from "@/types/navigation";
import type { QuestionPanelState } from "@/types/question";

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
  onOpenDebug: () => void;
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
  onOpenDebug,
}: WorkspaceContentProps) {
  return (
    <main className="min-h-0 flex-1 overflow-hidden bg-stone-50">
      {activeTab === "dashboard" && (
        <StudyDashboardPanel
          onStartChat={onJumpToChat}
          onGeneratePractice={onGenerateSimilarPractice}
          onOpenKnowledgeMap={onOpenKnowledgeGraph}
          onOpenDebug={onOpenDebug}
        />
      )}
      {activeTab === "chat" && (
        <ChatPanel
          state={chatState}
          setState={setChatState}
          onOpenKnowledgeGraph={onOpenKnowledgeGraph}
          onGenerateSimilarPractice={onGenerateSimilarPractice}
        />
      )}
      {activeTab === "practice" && <QuestionPanel state={questionState} setState={setQuestionState} />}
      {activeTab === "kgraph" && (
        <KnowledgeGraphPanel
          focusLabel={knowledgeGraphFocus}
          onJumpToChat={onJumpToChat}
          onJumpToQuestions={onGenerateSimilarPractice}
        />
      )}
      {activeTab === "debug" && <DebugPanel />}
    </main>
  );
}
