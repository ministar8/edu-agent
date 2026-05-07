export type Difficulty = "basic" | "medium" | "hard" | "mixed";

export type QuestionPanelState = {
  topic: string;
  count: number;
  difficulty: Difficulty;
  loading: boolean;
  result: string;
  resultTopic: string;
};

export type QuestionPanelProps = {
  state: QuestionPanelState;
  setState: React.Dispatch<React.SetStateAction<QuestionPanelState>>;
};
