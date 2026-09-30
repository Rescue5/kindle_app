import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type {
  AppSettings,
  BookOption,
  ConnectorStatus,
  LexemeOccurrence,
  LexemeRecord,
  LibraryResult,
  ProgressEvent,
  WordAnalysis,
} from "@/types";

const isTauri = () => typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export const defaultSettings: AppSettings = {
  theme: "system",
  language: "ru",
  default_export_format: "anki",
  app_data_path: ".app-data",
  llm_enabled: false,
  llm_model: "deepseek-v4-flash",
  llm_base_url: "https://api.dslab.tech/v1",
  obsidian_sync_enabled: false,
  obsidian_vault_path: "",
  obsidian_cards_path: "cards/Book Vocab",
  obsidian_backup_enabled: true,
};

export async function callBackend<T>(action: string, payload: unknown): Promise<T> {
  if (!isTauri()) return mockBackend<T>(action, payload);
  return invoke<T>("python_bridge", { action, payload });
}

export async function cancelBackend(jobId: string): Promise<boolean> {
  if (!isTauri()) {
    cancelledJobs.add(jobId);
    return true;
  }
  return invoke<boolean>("cancel_python_bridge", { jobId });
}

export async function listenProgress(handler: (event: ProgressEvent) => void): Promise<UnlistenFn> {
  if (!isTauri()) return () => undefined;
  return listen<ProgressEvent>("backend-progress", (event) => handler(event.payload));
}

const previewScenario = () => new URLSearchParams(window.location.search).get("scenario") ?? "mixed";

const baseWords = [
  ["admitting", "admit", "She knew the answer but shied from admitting it.", "The Mirror's Truth", "Michael R. Fletcher"],
  ["glimpse", "glimpse", "For a moment he caught a glimpse of the city below.", "The Night Reader", "Demo Library"],
  ["dread", "dread", "A quiet dread settled over the room.", "Shadows and Signals", "Demo Library"],
  ["submerged", "submerge", "He tried to submerge the memory before it surfaced again.", "The Night Reader", "Demo Library"],
  ["resilient", "resilient", "Her resilient spirit never broke.", "Shadows and Signals", "Demo Library"],
  ["vigilant", "vigilant", "They remained vigilant through the night.", "Shadows and Signals", "Demo Library"],
] as const;

function occurrence(index: number, source: LexemeOccurrence["source"] = "kindle"): LexemeOccurrence {
  const [word, , context, book, authors] = baseWords[index];
  return {
    id: `${source}-${index}`,
    source,
    word,
    context,
    book_key: book,
    book_title: book,
    authors,
    looked_up_at: source === "kindle" ? `2026-07-${String(10 - index).padStart(2, "0")}` : "",
  };
}

function analysis(lemma: string, score: number): WordAnalysis {
  return {
    base_form: lemma,
    pos: "offline",
    accepted: true,
    importance_score: score,
    importance_note: "Оценено локальными частотными и морфологическими правилами.",
    frequency_note: "Zipf 3.8",
    source_occurrence_count: 1,
    translation_status: "offline_only",
    warnings: [],
  };
}

function makeLexeme(index: number): LexemeRecord {
  const [word, lemma] = baseWords[index];
  const rejected = index === 5;
  const ready = index === 0 || index === 4;
  const inObsidian = index === 0 || index === 4;
  const localAnalysis = ready
    ? analysis(lemma, index === 0 ? 10 : 7)
    : rejected
      ? { ...analysis(lemma, 1), accepted: false, importance_note: "Отклонено локальными правилами." }
      : null;
  return {
    id: `lexeme-${lemma}`,
    lemma,
    display_form: word,
    language: "en",
    forms: word === lemma ? [word] : [word, lemma],
    occurrences: [occurrence(index)],
    freshness: index === 1 || index === 2 ? "new" : "known",
    processing: {
      state: rejected ? "rejected" : ready ? "ready" : "pending",
      analysis: localAnalysis,
      updated_at: ready || rejected ? "2026-07-10T10:00:00Z" : "",
      error: "",
    },
    sources: { kindle: true, legacy: false },
    destinations: {
      obsidian: {
        state: inObsidian ? "synced" : ready ? "missing" : "not_applicable",
        eligible: ready,
        reason: ready ? "" : rejected ? "rejected" : "waiting_processing",
        external_key: lemma,
        last_checked_at: "2026-07-10T10:00:00Z",
        last_synced_at: inObsidian ? "2026-07-10T10:00:00Z" : "",
      },
      anki: { state: "not_exported", last_exported_at: "" },
      quizlet: { state: "not_exported", last_exported_at: "" },
    },
    first_seen_at: "2026-07-10T10:00:00Z",
    last_seen_at: "2026-07-10T10:00:00Z",
    last_kindle_sync_id: "preview-sync",
  };
}

let mockEntries = baseWords.map((_, index) => makeLexeme(index));
const mockReview = new Map<string, { due_at: string; interval_days: number; repetitions: number; last_rating: string; reviewed_at: string }>();
const cancelledJobs = new Set<string>();
let mockFailureConsumed = false;

function mockReviewResult(limit = 20) {
  const now = Date.now();
  const eligible = mockEntries.filter((entry) => entry.processing.state === "ready" && entry.processing.analysis?.accepted);
  const due = eligible.filter((entry) => {
    const schedule = mockReview.get(entry.id);
    return !schedule?.due_at || Date.parse(schedule.due_at) <= now;
  });
  return {
    cards: due.slice(0, limit).map((entry) => ({
      lexeme_id: entry.id,
      lemma: entry.lemma,
      display_form: entry.display_form,
      analysis: entry.processing.analysis,
      occurrences: entry.occurrences,
      first_seen_at: entry.first_seen_at,
      review: mockReview.get(entry.id) ?? { due_at: "", interval_days: 0, repetitions: 0, last_rating: "", reviewed_at: "" },
    })),
    due_count: due.length,
    total_count: eligible.length,
  };
}

function mockConnectors(): ConnectorStatus {
  const scenario = previewScenario();
  return {
    kindle: {
      state: scenario === "disconnected" ? "disconnected" : "connected",
      label: scenario === "disconnected" ? "Kindle" : "Kindle Paperwhite",
      checked_at: new Date().toISOString(),
      signature: scenario === "disconnected" ? undefined : ["preview-kindle", "12345678", "2026-07-10T10:00:00Z"],
    },
    obsidian: {
      state: scenario === "obsidian-error" ? "error" : "connected",
      label: "Obsidian",
      checked_at: new Date().toISOString(),
    },
  };
}

function buildBooks(entries: LexemeRecord[]): BookOption[] {
  const counts = new Map<string, number>();
  const details = new Map<string, { title: string; authors: string }>();
  for (const entry of entries) {
    for (const key of new Set(entry.occurrences.map((item) => item.book_key).filter(Boolean))) {
      counts.set(key, (counts.get(key) ?? 0) + 1);
      const occurrence = entry.occurrences.find((item) => item.book_key === key);
      if (occurrence && !details.has(key)) details.set(key, { title: occurrence.book_title || key, authors: occurrence.authors });
    }
  }
  return [{ label: "Все книги", key: "" }, ...Array.from(counts, ([key, count]) => {
    const { title, authors } = details.get(key) ?? { title: key, authors: "" };
    return { label: `${title}${authors ? ` · ${authors}` : ""} · ${count}`, key, title, authors };
  })];
}

function libraryResult(): LibraryResult {
  const pending = mockEntries.filter((entry) => ["pending", "failed"].includes(entry.processing.state)).length;
  return {
    sourceName: "Preview library",
    sourceStatus: "Локальная библиотека готова",
    books: buildBooks(mockEntries),
    entries: mockEntries,
    last_kindle_sync_id: "preview-sync",
    connectors: mockConnectors(),
    queueStatus: { pending, processing: 0, failed: 0, total: pending },
  };
}

async function mockBackend<T>(action: string, payload: unknown): Promise<T> {
  const slowOperation = previewScenario() === "slow" && ["process_queue", "process_lexemes", "sync_obsidian"].includes(action);
  await new Promise((resolve) => setTimeout(resolve, action === "connector_status" ? 80 : slowOperation ? 2500 : 280));
  const requestJobId = (payload as { job_id?: string } | undefined)?.job_id;
  if (requestJobId && cancelledJobs.delete(requestJobId)) throw new Error("Операция отменена");
  if (previewScenario() === "operation-error" && action === "process_queue" && !mockFailureConsumed) {
    mockFailureConsumed = true;
    throw new Error("Тестовая ошибка offline-обработки");
  }
  if (action === "load_settings") return { ...defaultSettings, obsidian_sync_enabled: true, obsidian_vault_path: "preview" } as T;
  if (action === "save_settings") return { saved: true } as T;
  if (action === "connector_status") return mockConnectors() as T;
  if (["load_library", "load_cached", "sync_kindle", "scan", "download_covers"].includes(action)) return libraryResult() as T;
  if (action === "load_review") return mockReviewResult((payload as { limit?: number } | undefined)?.limit ?? 20) as T;
  if (action === "rate_review") {
    const { lexeme_id, rating } = payload as { lexeme_id: string; rating: "again" | "hard" | "good" };
    const previous = mockReview.get(lexeme_id);
    const interval = rating === "again" ? 0 : rating === "hard" ? Math.max(1, (previous?.interval_days ?? 0) * 1.2) : Math.max(3, (previous?.interval_days ?? 0) * 2.5);
    const now = new Date();
    mockReview.set(lexeme_id, { due_at: new Date(now.getTime() + (rating === "again" ? 10 * 60_000 : interval * 86_400_000)).toISOString(), interval_days: interval, repetitions: (previous?.repetitions ?? 0) + 1, last_rating: rating, reviewed_at: now.toISOString() });
    const result = mockReviewResult();
    return { card: result.cards.find((card) => card.lexeme_id === lexeme_id) ?? null, due_count: result.due_count, total_count: result.total_count } as T;
  }
  if (["process_queue", "process_lexemes", "optimize"].includes(action)) {
    const requested = (payload as { ids?: string[] })?.ids;
    const ids = new Set(requested ?? mockEntries.filter((entry) => ["pending", "failed"].includes(entry.processing.state)).map((entry) => entry.id));
    mockEntries = mockEntries.map((entry) =>
      ids.has(entry.id)
        ? {
            ...entry,
            processing: { state: "ready", analysis: analysis(entry.lemma, 6), updated_at: new Date().toISOString(), error: "" },
            destinations: {
              ...entry.destinations,
              obsidian: { ...entry.destinations.obsidian, state: "missing", eligible: true, reason: "" },
            },
          }
        : entry,
    );
    return { processed_new: ids.size, accepted_new: ids.size, rejected_new: 0, skipped_existing: 0, entries: mockEntries, queue_status: { pending: 0, processing: 0, failed: 0, total: 0 } } as T;
  }
  if (action === "sync_obsidian") {
    const pendingSync = mockEntries.filter((entry) => entry.destinations.obsidian.eligible && entry.destinations.obsidian.state === "missing");
    const items = pendingSync.map((entry) => ({ id: entry.id, outcome: "added", reason: "" }));
    mockEntries = mockEntries.map((entry) =>
      entry.destinations.obsidian.eligible
        ? { ...entry, destinations: { ...entry.destinations, obsidian: { ...entry.destinations.obsidian, state: "synced", reason: "", last_synced_at: new Date().toISOString() } } }
        : entry,
    );
    return { added: items.length, skipped: 0, files: ["Priority 7.md"], backup_path: "preview", items, entries: mockEntries, queue_status: { pending: 0, processing: 0, failed: 0, total: 0 } } as T;
  }
  if (action === "export") return { path: "preview/export.tsv", exported: (payload as { entries?: unknown[] })?.entries?.length ?? 0 } as T;
  return {} as T;
}
