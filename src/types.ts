export type BookOption = {
  label: string;
  key: string;
};

export type VocabEntry = {
  word: string;
  stem: string;
  context: string;
  book_key: string;
  book_title: string;
  authors: string;
  language: string;
  looked_up_at: string;
};

export type ActivityEvent = {
  phase: "ready" | "thinking" | "answered" | "failed" | string;
  title: string;
  message: string;
  meta?: string;
};

export type AppState = {
  sourceName: string;
  sourceStatus: string;
  statusMessage: string;
  dbLoaded: boolean;
  processing: boolean;
  books: BookOption[];
  selectedBookIndex: number;
  searchText: string;
  entries: VocabEntry[];
  activityEvents: ActivityEvent[];
};
