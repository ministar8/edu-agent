import { DebugPanel } from "@/features/admin-debug";
import { ChatPanel } from "@/features/chat";
import { StudyDashboardPanel } from "@/features/dashboard";
import { KnowledgeGraphPanel } from "@/features/knowledge-map";
import { QuestionPanel } from "@/features/practice";
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
    <main className="min-h-0 flex-1 overflow-hidden bg-[#F5F5F5]">
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
