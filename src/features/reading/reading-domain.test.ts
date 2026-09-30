import { describe, expect, it } from "vitest";
import type { LexemeRecord } from "@/types";
import { activityDays, bookStats, repeatedLookupStats, ruCount } from "./reading-domain";

function word(lemma: string, date: string, book: string, lookups: number): LexemeRecord {
  return {
    id: lemma,
    lemma,
    display_form: lemma,
    first_seen_at: date,
    occurrences: Array.from({ length: lookups }, (_, index) => ({
      id: `${lemma}-${index}`,
      source: "kindle" as const,
      word: lemma,
      context: `${lemma} in a real sentence`,
      book_key: book,
      book_title: book,
      authors: "Author",
      looked_up_at: date,
    })),
  } as LexemeRecord;
}

describe("reading metrics", () => {
  it("counts unique words separately from repeated Kindle lookups and uses the actual title", () => {
    const entries = [word("glimpse", "2026-09-26", "Book A", 2), word("forlorn", "2026-09-27", "Book A", 1)];
    const books = bookStats([{ key: "Book A", label: "Book A · 2" }], entries);
    expect(books[0]).toMatchObject({ book: { label: "Book A" }, wordCount: 2, lookupCount: 3, repeatedWordCount: 1 });
    expect(repeatedLookupStats(entries)).toEqual({ words: 1, extraLookups: 1 });
  });

  it("keeps daily activity tied to stored dates and declines Russian counts correctly", () => {
    const days = activityDays([word("dread", "2026-09-28", "Book B", 1)], 3);
    expect(days.map((day) => [day.date, day.firstSeen, day.lookups])).toEqual([
      ["2026-09-26", 0, 0], ["2026-09-27", 0, 0], ["2026-09-28", 1, 1],
    ]);
    expect([1, 3, 11, 21].map((value) => ruCount(value, "слово", "слова", "слов"))).toEqual(["слово", "слова", "слов", "слово"]);
  });
});
