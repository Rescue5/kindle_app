import type { BookOption, LexemeOccurrence, LexemeRecord, Operation, ProcessingState } from "@/types";

export type QuickFilter = "all" | "new" | "pending" | "ready" | "unsynced";

export const idleOperation: Operation = {
  id: "",
  kind: "idle",
  status: "idle",
  title: "Готово к работе",
  message: "Последняя операция не запускалась",
  current: 0,
  total: 0,
  stage: "idle",
  error: "",
};

export function primaryOccurrence(entry: LexemeRecord): LexemeOccurrence | undefined {
  return entry.occurrences.reduce<LexemeOccurrence | undefined>((best, item) => {
    if (!best) return item;
    const itemRank = [Boolean(item.context), item.context.length, item.looked_up_at].join("|");
    const bestRank = [Boolean(best.context), best.context.length, best.looked_up_at].join("|");
    return itemRank > bestRank ? item : best;
  }, undefined);
}

export function filterLexemes(
  entries: LexemeRecord[],
  query: string,
  selectedBook: BookOption | undefined,
  filter: QuickFilter,
): LexemeRecord[] {
  const normalizedQuery = query.trim().toLocaleLowerCase("ru");
  const selectedBookKey = selectedBook?.key ?? "";
  return entries
    .filter((entry) => {
      const bookMatch = !selectedBookKey || entry.occurrences.some((item) => item.book_key === selectedBookKey);
      const filterMatch =
        filter === "all" ||
        (filter === "new" && entry.freshness === "new") ||
        (filter === "pending" && ["pending", "failed"].includes(entry.processing.state)) ||
        (filter === "ready" && entry.processing.state === "ready") ||
        (filter === "unsynced" && entry.destinations.obsidian.state !== "synced");
      if (!bookMatch || !filterMatch) return false;
      if (!normalizedQuery) return true;
      const occurrenceText = entry.occurrences.flatMap((item) => [item.context, item.book_title, item.authors]);
      return [entry.display_form, entry.lemma, ...entry.forms, ...occurrenceText].some((value) =>
        value.toLocaleLowerCase("ru").includes(normalizedQuery),
      );
    })
    .sort((left, right) => {
      if (left.freshness !== right.freshness) return left.freshness === "new" ? -1 : 1;
      return right.last_seen_at.localeCompare(left.last_seen_at) || left.lemma.localeCompare(right.lemma);
    });
}

export function counts(entries: LexemeRecord[]) {
  return entries.reduce(
    (result, entry) => {
      result.all += 1;
      if (entry.freshness === "new") result.new += 1;
      if (["pending", "failed"].includes(entry.processing.state)) result.pending += 1;
      if (entry.processing.state === "ready") result.ready += 1;
      if (entry.destinations.obsidian.state !== "synced") result.unsynced += 1;
      return result;
    },
    { all: 0, new: 0, pending: 0, ready: 0, unsynced: 0 },
  );
}

export function processable(entries: LexemeRecord[]): LexemeRecord[] {
  return entries.filter((entry) => ["pending", "failed"].includes(entry.processing.state));
}

export function obsidianSyncReason(entry: LexemeRecord): string {
  if (entry.destinations.obsidian.state === "synced") return "Карточка находится в Obsidian";
  if (entry.processing.state === "pending") return "Сначала выполните offline-обработку";
  if (entry.processing.state === "processing") return "Обработка ещё выполняется";
  if (entry.processing.state === "rejected") return "Лемма отклонена локальными правилами";
  if (entry.processing.state === "failed") return "Исправьте ошибку обработки и повторите попытку";
  const score = entry.processing.analysis?.importance_score;
  if (typeof score !== "number" || score < 3 || score > 10) return "Приоритет не подходит для текущего шаблона Obsidian";
  return "Готово к синхронизации";
}

export function processingLabel(state: ProcessingState): string {
  return {
    pending: "Не обработано",
    processing: "Обрабатывается",
    ready: "Обработано",
    rejected: "Отклонено",
    failed: "Ошибка",
  }[state];
}

export function processingTone(state: ProcessingState): string {
  return {
    pending: "text-warning",
    processing: "text-primary",
    ready: "text-success",
    rejected: "text-muted-foreground",
    failed: "text-destructive",
  }[state];
}
