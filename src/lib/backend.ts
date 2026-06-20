import { invoke } from "@tauri-apps/api/core";
import type { ActivityEvent, AppState, BookOption, VocabEntry } from "@/types";

function rawEntry(entry: Omit<VocabEntry, "id" | "processing_status" | "export_status">): VocabEntry {
  const id = [entry.word, entry.book_key, entry.looked_up_at, entry.context].join("|");
  return {
    ...entry,
    id,
    processing_status: "raw",
    export_status: "none",
  };
}

const demoEntries: VocabEntry[] = [
  rawEntry({
    word: "afraid",
    stem: "afraid",
    context: "She was afraid to open the old door.",
    book_key: "demo-night",
    book_title: "The Night Reader",
    authors: "Demo Library",
    language: "en",
    looked_up_at: "2026-06-19",
  }),
  rawEntry({
    word: "glimpse",
    stem: "glimpse",
    context: "For a moment he caught a glimpse of the city below.",
    book_key: "demo-night",
    book_title: "The Night Reader",
    authors: "Demo Library",
    language: "en",
    looked_up_at: "2026-06-18",
  }),
  rawEntry({
    word: "dread",
    stem: "dread",
    context: "A quiet dread settled over the room.",
    book_key: "demo-shadow",
    book_title: "Shadows and Signals",
    authors: "Demo Library",
    language: "en",
    looked_up_at: "2026-06-17",
  }),
  rawEntry({
    word: "submerge",
    stem: "submerge",
    context: "He tried to submerge the memory before it surfaced again.",
    book_key: "demo-night",
    book_title: "The Night Reader",
    authors: "Demo Library",
    language: "en",
    looked_up_at: "2026-06-17",
  }),
  rawEntry({
    word: "resilient",
    stem: "resilient",
    context: "Her resilient spirit never broke.",
    book_key: "demo-shadow",
    book_title: "Shadows and Signals",
    authors: "Demo Library",
    language: "en",
    looked_up_at: "2026-06-16",
  }),
  rawEntry({
    word: "vigilant",
    stem: "vigilant",
    context: "They remained vigilant through the night.",
    book_key: "demo-shadow",
    book_title: "Shadows and Signals",
    authors: "Demo Library",
    language: "en",
    looked_up_at: "2026-06-15",
  }),
  rawEntry({
    word: "faint",
    stem: "faint",
    context: "A faint glow lit the corridor.",
    book_key: "demo-night",
    book_title: "The Night Reader",
    authors: "Demo Library",
    language: "en",
    looked_up_at: "2026-06-15",
  }),
  rawEntry({
    word: "meticulous",
    stem: "meticulous",
    context: "He kept meticulous notes in the margin.",
    book_key: "demo-shadow",
    book_title: "Shadows and Signals",
    authors: "Demo Library",
    language: "en",
    looked_up_at: "2026-06-14",
  }),
];

const demoBooks: BookOption[] = [
  { label: "Все книги", key: "" },
  { label: "The Night Reader · Demo Library · 4", key: "demo-night" },
  { label: "Shadows and Signals · Demo Library · 4", key: "demo-shadow" },
];

const demoEvents: ActivityEvent[] = [
  {
    phase: "ready",
    title: "Ожидание Kindle",
    message: "Подключите Kindle или используйте preview-данные. Слова остаются необработанными до offline-обработки.",
    meta: "Готово",
  },
];

export const initialState: AppState = {
  sourceName: "Preview workspace",
  sourceStatus: "Kindle не подключён · показаны демонстрационные слова",
  statusMessage: "Слова из Kindle Vocabulary Builder и подготовка карточек",
  dbLoaded: true,
  processing: false,
  books: demoBooks,
  selectedBookIndex: 0,
  searchText: "",
  entries: demoEntries,
  activityEvents: demoEvents,
};

export async function callBackend<T>(action: string, payload: unknown): Promise<T> {
  if (!("__TAURI_INTERNALS__" in window)) {
    return mockBackend<T>(action, payload);
  }
  return invoke<T>("python_bridge", { action, payload });
}

async function mockBackend<T>(action: string, payload: unknown): Promise<T> {
  await new Promise((resolve) => setTimeout(resolve, 320));
  if (action === "scan" || action === "load_demo") {
    return {
      sourceName: action === "scan" ? "Demo Kindle Paperwhite" : "Demo Kindle",
      sourceStatus: "Preview-словарь загружен",
      books: demoBooks,
      entries: demoEntries.map((entry) => ({ ...entry, processing_status: "raw", analysis: undefined })),
    } as T;
  }
  if (action === "optimize") {
    const entries = (payload as { entries?: VocabEntry[] })?.entries ?? demoEntries;
    return {
      accepted_new: entries.length,
      processed_new: entries.length,
      skipped_existing: 0,
      rejected_new: 0,
      tsv_path: "preview/optimized.tsv",
      entry_updates: entries.map((entry) => ({
        id: entry.id,
        processing_status: "processed",
        analysis: {
          base_form: entry.stem || entry.word,
          pos: "offline",
          accepted: true,
          importance_score: Math.max(2, Math.min(8, Math.round(entry.word.length * 0.7))),
          importance_note: "оценено локальными правилами",
          frequency_note: "offline-анализ без перевода",
          warnings: [],
          source_occurrence_count: 1,
          translation_status: "offline_only",
          tsv_path: "preview/optimized.tsv",
        },
      })),
      events: [
        {
          phase: "answered",
          title: "Offline processing",
          message: `${entries.length} слов получили локальную оценку сложности и базовую форму.`,
          meta: "Python",
        },
      ],
    } as T;
  }
  if (action === "export") {
    return { path: "preview/export.tsv" } as T;
  }
  return {} as T;
}
