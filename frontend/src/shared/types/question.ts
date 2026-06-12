export type Difficulty = "basic" | "medium" | "hard" | "mixed";

export type StructuredQuestion = {
  question_type: string;
  difficulty: number;
  stem: string;
  answer: string;
  explanation: string;
  // Frontend-only state
  id?: number;           // from DB after persist
  gradingStatus?: "idle" | "loading" | "done";
  userAnswer?: string;
  gradingScore?: number;
  gradingFeedback?: string;
  isWrong?: boolean;
};

export type WrongQuestion = {
  id: number;
  question_type: string | null;
  difficulty: number;
  stem: string;
  standard_answer: string | null;
  explanation: string | null;
  user_answer: string | null;
  grading_score: number | null;
  error_analysis: string;
  redo_count: number;
  created_at: string;
  // Frontend-only redo state
  redoAnswer?: string;
  redoStatus?: "idle" | "loading" | "done";
  redoScore?: number;
  redoFeedback?: string;
  redoIsWrong?: boolean;
  redoErrorAnalysis?: string;
};

export type QuestionPanelState = {
  topic: string;
  count: number;
  difficulty: Difficulty;
  loading: boolean;
  result: string;
  resultTopic: string;
  questions: StructuredQuestion[];
  wrongQuestions: WrongQuestion[];
  wrongLoading: boolean;
  activeTab: "generate" | "wrong";
};

export type QuestionPanelProps = {
  state: QuestionPanelState;
  setState: React.Dispatch<React.SetStateAction<QuestionPanelState>>;
};
