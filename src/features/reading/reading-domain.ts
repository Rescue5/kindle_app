import type { BookOption, LexemeOccurrence, LexemeRecord } from "@/types";

export type BookStats = {
  book: BookOption;
  author: string;
  words: LexemeRecord[];
  wordCount: number;
  lookupCount: number;
  repeatedWordCount: number;
  repeatedLookupCount: number;
  lastLookupAt: string;
};

export type ActivityDay = {
  date: string;
  firstSeen: number;
  lookups: number;
};

export function ruCount(value: number, one: string, few: string, many: string): string {
  const lastTwo = Math.abs(value) % 100;
  const last = lastTwo % 10;
  if (lastTwo >= 11 && lastTwo <= 14) return many;
  if (last === 1) return one;
  if (last >= 2 && last <= 4) return few;
  return many;
}

export function dateKey(value: string): string | null {
  if (!value) return null;
  const match = /^(\d{4}-\d{2}-\d{2})/.exec(value);
  if (!match) return null;
  const date = new Date(`${match[1]}T00:00:00Z`);
  return Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== match[1] ? null : match[1];
}

export function formatDate(value: string, options?: Intl.DateTimeFormatOptions): string {
  const key = dateKey(value);
  if (!key) return "Дата неизвестна";
  return new Intl.DateTimeFormat("ru-RU", { timeZone: "UTC", ...(options ?? { day: "numeric", month: "short", year: "numeric" }) }).format(
    new Date(`${key}T12:00:00Z`),
  );
}

export function bookStats(books: BookOption[], entries: LexemeRecord[]): BookStats[] {
  const byKey = new Map<string, BookStats>();
  for (const book of books) {
    if (!book.key || byKey.has(book.key)) continue;
    byKey.set(book.key, {
      book,
      author: "",
      words: [],
      wordCount: 0,
      lookupCount: 0,
      repeatedWordCount: 0,
      repeatedLookupCount: 0,
      lastLookupAt: "",
    });
  }

  for (const entry of entries) {
    const grouped = new Map<string, LexemeOccurrence[]>();
    for (const occurrence of entry.occurrences) {
      if (!occurrence.book_key) continue;
      const current = grouped.get(occurrence.book_key);
      if (current) current.push(occurrence);
      else grouped.set(occurrence.book_key, [occurrence]);
    }
    for (const [key, occurrences] of grouped) {
      let stats = byKey.get(key);
      if (!stats) {
        stats = {
          book: { key, label: occurrences.find((item) => item.book_title)?.book_title || "Без названия" },
          author: "",
          words: [],
          wordCount: 0,
          lookupCount: 0,
          repeatedWordCount: 0,
          repeatedLookupCount: 0,
          lastLookupAt: "",
        };
        byKey.set(key, stats);
      }
      const title = occurrences.find((item) => item.book_title)?.book_title;
      if (title) stats.book = { ...stats.book, label: stats.book.display_title || title };
      stats.words.push(entry);
      stats.wordCount += 1;
      stats.lookupCount += occurrences.length;
      if (occurrences.length > 1) {
        stats.repeatedWordCount += 1;
        stats.repeatedLookupCount += occurrences.length - 1;
      }
      for (const occurrence of occurrences) {
        if (!stats.author && occurrence.authors) stats.author = occurrence.authors;
        if (dateKey(occurrence.looked_up_at) && occurrence.looked_up_at > stats.lastLookupAt) {
          stats.lastLookupAt = occurrence.looked_up_at;
        }
      }
    }
  }
  return [...byKey.values()].sort((left, right) =>
    right.lastLookupAt.localeCompare(left.lastLookupAt) || left.book.label.localeCompare(right.book.label, "ru"),
  );
}

export function lookupsForBook(entry: LexemeRecord, bookKey: string): LexemeOccurrence[] {
  return entry.occurrences.filter((occurrence) => occurrence.book_key === bookKey);
}

export function activityDays(entries: LexemeRecord[], count = 14): ActivityDay[] {
  const byDate = new Map<string, ActivityDay>();
  const add = (date: string, field: "firstSeen" | "lookups") => {
    const current = byDate.get(date) ?? { date, firstSeen: 0, lookups: 0 };
    current[field] += 1;
    byDate.set(date, current);
  };
  for (const entry of entries) {
    const firstSeen = dateKey(entry.first_seen_at);
    if (firstSeen) add(firstSeen, "firstSeen");
    for (const occurrence of entry.occurrences) {
      const lookedUp = dateKey(occurrence.looked_up_at);
      if (lookedUp) add(lookedUp, "lookups");
    }
  }
  const latest = [...byDate.keys()].sort().at(-1);
  if (!latest) return [];
  const days: ActivityDay[] = [];
  const end = new Date(`${latest}T00:00:00Z`).getTime();
  for (let offset = Math.max(1, count) - 1; offset >= 0; offset -= 1) {
    const date = new Date(end - offset * 86_400_000).toISOString().slice(0, 10);
    days.push(byDate.get(date) ?? { date, firstSeen: 0, lookups: 0 });
  }
  return days;
}

export function repeatedLookupStats(entries: LexemeRecord[]): { words: number; extraLookups: number } {
  let words = 0;
  let extraLookups = 0;
  for (const entry of entries) {
    if (entry.occurrences.length > 1) {
      words += 1;
      extraLookups += entry.occurrences.length - 1;
    }
  }
  return { words, extraLookups };
}
