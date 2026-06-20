export type BookOption = {
  label: string;
  key: string;
};

export type VocabEntry = {
  id: string;
  word: string;
  stem: string;
  context: string;
  book_key: string;
  book_title: string;
  authors: string;
  language: string;
  looked_up_at: string;
  processing_status?: ProcessingStatus;
  analysis?: WordAnalysis;
  export_status?: "none" | "queued" | "exported" | "failed";
};

export type ProcessingStatus = "raw" | "processing" | "processed" | "rejected" | "skipped" | "failed";

export type WordAnalysis = {
  base_form: string;
  pos?: string;
  accepted: boolean;
  importance_score?: number;
  importance_note?: string;
  frequency_note?: string;
  warnings?: string[];
  source_occurrence_count?: number;
  processed_at?: string;
  tsv_path?: string;
  translation_status?: "not_started" | "offline_only" | "llm_enriched";
  russian_meanings?: string;
  generated_context_en?: string;
  generated_context_ru?: string;
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
