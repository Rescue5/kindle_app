import { invoke } from "@tauri-apps/api/core";
import type { ActivityEvent, AppSettings, AppState, BookOption, VocabEntry } from "@/types";

function rawEntry(entry: Omit<VocabEntry, "id" | "processing_status" | "export_status">): VocabEntry {
  const id = [entry.word, entry.book_key, entry.looked_up_at, entry.context].join("|");
  return {
    ...entry,
    id,
    processing_status: "raw",
    export_status: "none",
  };
}

const baseDemoEntries: VocabEntry[] = [
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

const demoEntries = buildDemoEntries(getPreviewEntryCount());
const demoBooks = buildDemoBooks(demoEntries);

function getPreviewEntryCount() {
  if (typeof window === "undefined") return baseDemoEntries.length;
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("demoRows") ?? (params.has("stress") ? "1200" : "");
  const parsed = Number(requested);
  if (!Number.isFinite(parsed) || parsed <= baseDemoEntries.length) return baseDemoEntries.length;
  return Math.min(2500, Math.round(parsed));
}

function buildDemoEntries(count: number) {
  const entries = [...baseDemoEntries];
  for (let index = entries.length; index < count; index += 1) {
    const seed = baseDemoEntries[index % baseDemoEntries.length];
    if (index % 83 === 0) {
      entries.push({ ...seed });
      continue;
    }
    const sequence = index + 1;
    entries.push(
      rawEntry({
        word: seed.word,
        stem: seed.stem,
        context: `${seed.context} Preview occurrence ${sequence}.`,
        book_key: seed.book_key,
        book_title: seed.book_title,
        authors: seed.authors,
        language: seed.language,
        looked_up_at: `2026-06-${String((index % 28) + 1).padStart(2, "0")}`,
      }),
    );
  }
  return entries;
}

function buildDemoBooks(entries: VocabEntry[]): BookOption[] {
  const counts = entries.reduce(
    (acc, entry) => acc.set(entry.book_key, (acc.get(entry.book_key) ?? 0) + 1),
    new Map<string, number>(),
  );
  return [
    { label: "Все книги", key: "" },
    { label: `The Night Reader · Demo Library · ${counts.get("demo-night") ?? 0}`, key: "demo-night" },
    { label: `Shadows and Signals · Demo Library · ${counts.get("demo-shadow") ?? 0}`, key: "demo-shadow" },
  ];
}

const demoEvents: ActivityEvent[] = [
  {
    phase: "ready",
    title: "Ожидание Kindle",
    message: "Подключите Kindle или используйте preview-данные. Слова остаются необработанными до offline-обработки.",
    meta: "Готово",
  },
];

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
  settings: defaultSettings,
  currentView: "library",
};

export async function callBackend<T>(action: string, payload: unknown): Promise<T> {
  if (!("__TAURI_INTERNALS__" in window)) {
    return mockBackend<T>(action, payload);
  }
  return invoke<T>("python_bridge", { action, payload });
}

async function mockBackend<T>(action: string, payload: unknown): Promise<T> {
  await new Promise((resolve) => setTimeout(resolve, 320));
  if (action === "load_settings") {
    return { ...defaultSettings } as T;
  }
  if (action === "save_settings") {
    return { saved: true } as T;
  }
  if (action === "load_obsidian") {
    return {
      sourceName: "Demo Obsidian vault",
      sourceStatus: "Preview-словарь загружен из Obsidian",
      books: demoBooks,
      entries: demoEntries.map((entry) => ({ ...entry, processing_status: "processed", analysis: undefined })),
    } as T;
  }
  if (action === "sync_obsidian") {
    return { added: 0, skipped: 0, files: [], backup_path: "preview/backup" } as T;
  }
  if (action === "scan" || action === "load_demo" || action === "load_cached") {
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
          frequency_note: "lemma Zipf 3.8, form Zipf 3.6",
          lemma_zipf: 3.8,
          form_zipf: 3.6,
          wordnet_synset_count: 4,
          wordnet_pos_count: 2,
          warnings: [],
          tags: "priority_medium preview",
          source_word_forms: [entry.word],
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
    const entries = (payload as { entries?: VocabEntry[] })?.entries ?? [];
    return { path: "preview/export.tsv", exported: entries.length } as T;
  }
  return {} as T;
}
