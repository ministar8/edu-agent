export type Difficulty = "basic" | "medium" | "hard" | "mixed";

export type StructuredQuestion = {
  question_type: string;
  difficulty: number;
  stem: string;
  answer: string;
  explanation: string;
  quality_score?: number;
  batch_id?: string;
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
  created_at: string;
};

export type QuestionPanelState = {
  topic: string;
  count: number;
  difficulty: Difficulty;
  loading: boolean;
  result: string;
  resultTopic: string;
  questions: StructuredQuestion[];
  batchId: string | null;
  wrongQuestions: WrongQuestion[];
  wrongLoading: boolean;
  activeTab: "generate" | "wrong";
};

export type QuestionPanelProps = {
  state: QuestionPanelState;
  setState: React.Dispatch<React.SetStateAction<QuestionPanelState>>;
};
