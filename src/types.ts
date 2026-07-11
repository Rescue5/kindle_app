export type BookOption = {
  label: string;
  key: string;
};

export type OccurrenceSource = "kindle" | "obsidian" | "legacy";

export type LexemeOccurrence = {
  id: string;
  source: OccurrenceSource;
  word: string;
  context: string;
  book_key: string;
  book_title: string;
  authors: string;
  looked_up_at: string;
};

export type Freshness = "new" | "known";
export type ProcessingState = "pending" | "processing" | "ready" | "rejected" | "failed";
export type SyncState = "not_synced" | "syncing" | "synced" | "failed";
export type ExportState = "not_exported" | "exporting" | "exported" | "failed";

export type WordAnalysis = {
  base_form: string;
  pos?: string;
  accepted: boolean;
  importance_score?: number;
  importance_note?: string;
  frequency_note?: string;
  lemma_zipf?: number;
  form_zipf?: number;
  wordnet_synset_count?: number;
  wordnet_pos_count?: number;
  warnings?: string[];
  tags?: string;
  source_word_forms?: string[];
  source_occurrence_count?: number;
  processed_at?: string;
  tsv_path?: string;
  translation_status?: "not_started" | "offline_only" | "llm_enriched";
  russian_meanings?: string;
  generated_context_en?: string;
  generated_context_ru?: string;
};

export type LexemeRecord = {
  id: string;
  lemma: string;
  display_form: string;
  language: string;
  forms: string[];
  occurrences: LexemeOccurrence[];
  freshness: Freshness;
  processing: {
    state: ProcessingState;
    analysis?: WordAnalysis | null;
    updated_at: string;
    error: string;
  };
  sources: {
    kindle: boolean;
    obsidian: boolean;
    legacy: boolean;
  };
  destinations: {
    obsidian: {
      state: SyncState;
      reason: string;
      last_synced_at: string;
    };
    anki: {
      state: ExportState;
      last_exported_at: string;
    };
    quizlet: {
      state: ExportState;
      last_exported_at: string;
    };
  };
  first_seen_at: string;
  last_seen_at: string;
  last_kindle_sync_id: string;
};

export type ConnectorState = "unknown" | "checking" | "connected" | "disconnected" | "disabled" | "error";

export type ConnectorInfo = {
  state: ConnectorState;
  label: string;
  checked_at: string;
};

export type ConnectorStatus = {
  kindle: ConnectorInfo;
  obsidian: ConnectorInfo;
};

export type LibraryResult = {
  sourceName: string;
  sourceStatus: string;
  books: BookOption[];
  entries: LexemeRecord[];
  last_kindle_sync_id: string;
  connectors: ConnectorStatus;
};

export type ProgressEvent = {
  job_id: string;
  stage: string;
  message: string;
  current: number;
  total: number;
  lexeme_id: string;
  timestamp: string;
};

export type ActivityEvent = {
  phase: "ready" | "thinking" | "answered" | "failed" | string;
  title: string;
  message: string;
  meta?: string;
};

export type AppSettings = {
  theme: "system" | "light" | "dark";
  language: "ru" | "en";
  default_export_format: "anki" | "quizlet";
  app_data_path: string;
  llm_enabled: boolean;
  llm_model: string;
  llm_base_url: string;
  obsidian_sync_enabled: boolean;
  obsidian_vault_path: string;
  obsidian_cards_path: string;
  obsidian_backup_enabled: boolean;
};

export type OperationKind = "idle" | "kindle" | "processing" | "obsidian" | "export";
export type OperationStatus = "idle" | "running" | "completed" | "cancelled" | "error";

export type Operation = {
  id: string;
  kind: OperationKind;
  status: OperationStatus;
  title: string;
  message: string;
  current: number;
  total: number;
  stage: string;
  error: string;
};
