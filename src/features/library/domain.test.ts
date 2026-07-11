import { describe, expect, it } from "vitest";
import { counts, filterLexemes, obsidianSyncReason } from "./domain";
import type { LexemeRecord } from "@/types";

const entry = {
  id: "one",
  lemma: "admit",
  display_form: "admitting",
  language: "en",
  forms: ["admit", "admitting"],
  occurrences: [{ id: "occ", source: "kindle", word: "admitting", context: "She admitted it.", book_key: "book", book_title: "Book", authors: "Author", looked_up_at: "2026-07-10" }],
  freshness: "new",
  processing: { state: "pending", analysis: null, updated_at: "", error: "" },
  sources: { kindle: true, obsidian: false, legacy: false },
  destinations: {
    obsidian: { state: "not_synced", reason: "waiting_processing", last_synced_at: "" },
    anki: { state: "not_exported", last_exported_at: "" },
    quizlet: { state: "not_exported", last_exported_at: "" },
  },
  first_seen_at: "2026-07-10",
  last_seen_at: "2026-07-10",
  last_kindle_sync_id: "sync",
} satisfies LexemeRecord;

describe("library selectors", () => {
  it("keeps freshness, processing and sync counts independent", () => {
    expect(counts([entry])).toEqual({ all: 1, new: 1, pending: 1, ready: 0, unsynced: 1 });
  });

  it("filters by occurrence book and context", () => {
    expect(filterLexemes([entry], "admitted", { key: "book", label: "Book" }, "all")).toHaveLength(1);
    expect(filterLexemes([entry], "missing", { key: "book", label: "Book" }, "all")).toHaveLength(0);
  });

  it("explains why an unsynced pending lexeme is blocked", () => {
    expect(obsidianSyncReason(entry)).toBe("Сначала выполните offline-обработку");
  });
});
