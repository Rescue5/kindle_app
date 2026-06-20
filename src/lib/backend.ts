import { invoke } from "@tauri-apps/api/core";
import type { ActivityEvent, AppState, BookOption, VocabEntry } from "@/types";

const demoEntries: VocabEntry[] = [
  {
    word: "afraid",
    stem: "afraid",
    context: "She was afraid to open the old door.",
    book_key: "demo-night",
    book_title: "The Night Reader",
    authors: "Demo Library",
    language: "en",
    looked_up_at: "2026-06-19",
  },
  {
    word: "glimpse",
    stem: "glimpse",
    context: "For a moment he caught a glimpse of the city below.",
    book_key: "demo-night",
    book_title: "The Night Reader",
    authors: "Demo Library",
    language: "en",
    looked_up_at: "2026-06-18",
  },
  {
    word: "dread",
    stem: "dread",
    context: "A quiet dread settled over the room.",
    book_key: "demo-shadow",
    book_title: "Shadows and Signals",
    authors: "Demo Library",
    language: "en",
    looked_up_at: "2026-06-17",
  },
  {
    word: "submerge",
    stem: "submerge",
    context: "He tried to submerge the memory before it surfaced again.",
    book_key: "demo-night",
    book_title: "The Night Reader",
    authors: "Demo Library",
    language: "en",
    looked_up_at: "2026-06-17",
  },
  {
    word: "resilient",
    stem: "resilient",
    context: "Her resilient spirit never broke.",
    book_key: "demo-shadow",
    book_title: "Shadows and Signals",
    authors: "Demo Library",
    language: "en",
    looked_up_at: "2026-06-16",
  },
  {
    word: "vigilant",
    stem: "vigilant",
    context: "They remained vigilant through the night.",
    book_key: "demo-shadow",
    book_title: "Shadows and Signals",
    authors: "Demo Library",
    language: "en",
    looked_up_at: "2026-06-15",
  },
  {
    word: "faint",
    stem: "faint",
    context: "A faint glow lit the corridor.",
    book_key: "demo-night",
    book_title: "The Night Reader",
    authors: "Demo Library",
    language: "en",
    looked_up_at: "2026-06-15",
  },
  {
    word: "meticulous",
    stem: "meticulous",
    context: "He kept meticulous notes in the margin.",
    book_key: "demo-shadow",
    book_title: "Shadows and Signals",
    authors: "Demo Library",
    language: "en",
    looked_up_at: "2026-06-14",
  },
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
    message: "Можно подключить устройство или открыть preview-набор для проверки интерфейса.",
    meta: "Готово",
  },
  {
    phase: "answered",
    title: "Конвейер готов",
    message: "Этапы обработки показывают фактические результаты: лемму, сложность, смысл и экспорт.",
    meta: "Система",
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
      entries: demoEntries,
    } as T;
  }
  if (action === "optimize") {
    const entries = (payload as { entries?: VocabEntry[] })?.entries ?? demoEntries;
    return {
      accepted_new: entries.length,
      processed_new: entries.length,
      skipped_existing: 0,
      tsv_path: "preview/optimized.tsv",
      events: [
        {
          phase: "thinking",
          title: "afraid",
          message: "Контекст указывает на эмоциональное состояние, а не на физическую опасность.",
          meta: "Анализ",
        },
        {
          phase: "answered",
          title: "glimpse",
          message: "Значение отличается от буквального «взгляд»: кратковременное восприятие.",
          meta: "B1+",
        },
      ],
    } as T;
  }
  if (action === "export") {
    return { path: "preview/export.tsv" } as T;
  }
  return {} as T;
}
