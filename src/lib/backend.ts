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
];

const demoBooks: BookOption[] = [
  { label: "Все книги", key: "" },
  { label: "The Night Reader · Demo Library · 2", key: "demo-night" },
  { label: "Shadows and Signals · Demo Library · 1", key: "demo-shadow" },
];

const demoEvents: ActivityEvent[] = [
  {
    phase: "ready",
    title: "Design system online",
    message: "React, Tailwind and Tauri shell are ready. Python bridge will provide live Kindle data.",
    meta: "Preview",
  },
  {
    phase: "answered",
    title: "DeepSeek enrichment",
    message: "Model reasoning and generated contexts appear here as compact operational events.",
    meta: "AI",
  },
];

export const initialState: AppState = {
  sourceName: "Demo workspace",
  sourceStatus: "Tauri bridge не активен в браузере · показан preview UI",
  statusMessage: "Premium interface preview",
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
      sourceName: "Demo Kindle",
      sourceStatus: "Preview data loaded",
      books: demoBooks,
      entries: demoEntries,
    } as T;
  }
  if (action === "optimize") {
    return {
      accepted_new: 3,
      processed_new: 3,
      skipped_existing: 0,
      tsv_path: "preview/optimized.tsv",
      events: [
        {
          phase: "thinking",
          title: "afraid",
          message: "Selecting the learner-friendly sense and translating context.",
          meta: "AI reasoning",
        },
        {
          phase: "answered",
          title: "glimpse",
          message: "Generated a concise card context and revised importance to 6/10.",
          meta: "Importance 6/10",
        },
      ],
    } as T;
  }
  if (action === "export") {
    return { path: "preview/export.tsv" } as T;
  }
  return {} as T;
}
