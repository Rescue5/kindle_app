import { useMemo } from "react";
import { ArrowRight, BarChart3, BookOpen, Repeat2 } from "lucide-react";
import type { BookOption, LexemeRecord } from "@/types";
import { activityDays, bookStats, dateKey, formatDate, repeatedLookupStats, ruCount } from "./reading-domain";

export type InsightsViewProps = {
  books: BookOption[];
  entries: LexemeRecord[];
  onOpenWord?: (entry: LexemeRecord) => void;
};

export function InsightsView({ books, entries, onOpenWord }: InsightsViewProps) {
  const bookData = useMemo(() => bookStats(books, entries), [books, entries]);
  const activity = useMemo(() => activityDays(entries), [entries]);
  const repeats = useMemo(() => repeatedLookupStats(entries), [entries]);
  const totalLookups = useMemo(() => entries.reduce((sum, entry) => sum + entry.occurrences.length, 0), [entries]);
  const datedFirstSeen = useMemo(() => entries.reduce((sum, entry) => sum + (dateKey(entry.first_seen_at) ? 1 : 0), 0), [entries]);
  const mostRepeated = useMemo(() => entries
    .filter((entry) => entry.occurrences.length > 1)
    .sort((left, right) => right.occurrences.length - left.occurrences.length || left.lemma.localeCompare(right.lemma))
    .slice(0, 5), [entries]);
  const maxDaily = Math.max(1, ...activity.flatMap((day) => [day.firstSeen, day.lookups]));
  const activeDays = activity.filter((day) => day.firstSeen > 0 || day.lookups > 0).length;

  return (
    <div className="app-scrollbar h-full overflow-y-auto bg-background px-5 py-6 text-foreground sm:px-8 lg:px-10">
      <div className="mx-auto max-w-[1280px]">
        <header className="mb-7 border-b border-border pb-6">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-primary">Следы чтения</p>
          <h1 className="font-serif text-4xl leading-tight tracking-tight sm:text-5xl">Как растёт словарь</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">Данные о словах, книгах и обращениях к словарю из вашей локальной библиотеки.</p>
        </header>

        {entries.length === 0 ? (
          <div className="flex min-h-[340px] flex-col items-center justify-center rounded-[var(--radius)] border border-dashed border-border bg-card px-6 text-center">
            <BarChart3 className="mb-4 h-9 w-9 text-primary" strokeWidth={1.5} />
            <h2 className="font-serif text-2xl">Пока нечего анализировать</h2>
            <p className="mt-2 max-w-md text-sm text-muted-foreground">Когда слова из Kindle появятся в библиотеке, здесь отобразятся реальные обращения и их даты.</p>
          </div>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Metric label="Слов в библиотеке" value={entries.length} detail="уникальных лемм" />
              <Metric label="Записей обращений" value={totalLookups} detail="из сохранённых контекстов" />
              <Metric label="Книг" value={bookData.filter((item) => item.lookupCount > 0).length} detail="с найденными словами" />
              <Metric label="Повторных обращений" value={repeats.extraLookups} detail={`${repeats.words} ${ruCount(repeats.words, "слово искали", "слова искали", "слов искали")} больше раза`} />
            </div>

            <section className="mt-7 rounded-[var(--radius)] border border-border bg-card p-5 sm:p-7">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h2 className="font-serif text-2xl">Слова и обращения по дням</h2>
                  <p className="mt-1 text-xs text-muted-foreground">14 календарных дней до последней записи · даты добавления слов и обращений к словарю</p>
                </div>
                <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-sm bg-primary" />Новые слова</span>
                  <span className="inline-flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-sm bg-accent" />Обращения</span>
                </div>
              </div>

              {activity.length === 0 ? (
                <div className="mt-5 rounded-[var(--radius)] border border-dashed border-border px-5 py-10 text-center text-sm text-muted-foreground">
                  У записей нет дат first_seen или looked_up_at. Временную динамику пока нельзя показать.
                </div>
              ) : (
                <>
                  <div className="mt-7 flex h-[192px] items-end gap-1 border-b border-border pb-2 sm:gap-2" role="img" aria-label={`За последние 14 дней с доступными датами: ${activeDays} дней с записями`}>
                    {activity.map((day, index) => (
                      <div key={day.date} className="group relative flex h-full min-w-0 flex-1 items-end justify-center gap-[2px] sm:gap-1" title={`${formatDate(day.date)}: ${day.firstSeen} новых слов, ${day.lookups} обращений`}>
                        <div className="w-[44%] max-w-5 rounded-t-sm bg-primary transition-opacity group-hover:opacity-75" style={{ height: day.firstSeen ? `${Math.max(2, day.firstSeen / maxDaily * 100)}%` : 0 }} />
                        <div className="w-[44%] max-w-5 rounded-t-sm bg-accent transition-opacity group-hover:opacity-75" style={{ height: day.lookups ? `${Math.max(2, day.lookups / maxDaily * 100)}%` : 0 }} />
                        {index % 3 === 0 || index === activity.length - 1 ? <span className="absolute -bottom-6 left-1/2 -translate-x-1/2 whitespace-nowrap text-[10px] tabular-nums text-muted-foreground">{formatDate(day.date, { day: "numeric", month: "short" })}</span> : null}
                      </div>
                    ))}
                  </div>
                  <div className="mt-9 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-4 text-xs text-muted-foreground">
                    <span>{activeDays} {ruCount(activeDays, "день", "дня", "дней")} с записями за показанный период</span>
                    <span>Последняя запись: {formatDate(activity[activity.length - 1].date)}</span>
                  </div>
                </>
              )}
            </section>

            <div className="mt-7 grid gap-7 xl:grid-cols-2">
              <section className="rounded-[var(--radius)] border border-border bg-card p-5 sm:p-6">
                <div className="flex items-center gap-3">
                  <BookOpen className="h-5 w-5 text-primary" strokeWidth={1.7} />
                  <h2 className="font-serif text-2xl">По книгам</h2>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">Разные слова и все сохранённые обращения.</p>
                {bookData.filter((item) => item.lookupCount > 0).length === 0 ? (
                  <p className="mt-5 rounded-[var(--radius)] border border-dashed border-border px-5 py-9 text-center text-sm text-muted-foreground">У слов ещё нет привязки к книгам.</p>
                ) : (
                  <div className="mt-5 divide-y divide-border">
                    {bookData.filter((item) => item.lookupCount > 0).map((item) => (
                      <div key={item.book.key} className="flex items-center gap-4 py-3 first:pt-0 last:pb-0">
                        <div className="flex h-12 w-9 shrink-0 items-center justify-center rounded-sm bg-primary font-serif text-lg text-primary-foreground">{item.book.label.slice(0, 1).toLocaleUpperCase()}</div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-serif text-base">{item.book.label}</p>
                          <p className="truncate text-xs text-muted-foreground">{item.author || "Автор не указан"}</p>
                        </div>
                        <div className="shrink-0 text-right text-xs tabular-nums"><strong className="block font-medium">{item.wordCount} {ruCount(item.wordCount, "слово", "слова", "слов")}</strong><span className="text-muted-foreground">{item.lookupCount} {ruCount(item.lookupCount, "обращение", "обращения", "обращений")}</span></div>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              <section className="rounded-[var(--radius)] border border-border bg-card p-5 sm:p-6">
                <div className="flex items-center gap-3">
                  <Repeat2 className="h-5 w-5 text-primary" strokeWidth={1.7} />
                  <h2 className="font-serif text-2xl">Слова, к которым возвращались</h2>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">Повторное обращение — каждая запись после первой для того же слова.</p>
                {mostRepeated.length === 0 ? (
                  <p className="mt-5 rounded-[var(--radius)] border border-dashed border-border px-5 py-9 text-center text-sm text-muted-foreground">Повторных обращений пока нет.</p>
                ) : (
                  <div className="mt-5 divide-y divide-border">
                    {mostRepeated.map((entry) => {
                      const content = (
                        <>
                          <span className="min-w-0 flex-1 truncate font-serif text-lg">{entry.display_form || entry.lemma}</span>
                          <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{entry.occurrences.length} {ruCount(entry.occurrences.length, "обращение", "обращения", "обращений")}</span>
                          {onOpenWord ? <ArrowRight aria-hidden="true" className="h-4 w-4 shrink-0 text-muted-foreground group-hover:text-primary" /> : null}
                        </>
                      );
                      return onOpenWord ? (
                        <button key={entry.id} type="button" onClick={() => onOpenWord(entry)} className="group flex w-full items-center gap-3 py-3 text-left transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:opacity-70 first:pt-0 last:pb-0">{content}</button>
                      ) : (
                        <div key={entry.id} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">{content}</div>
                      );
                    })}
                  </div>
                )}
              </section>
            </div>
            {datedFirstSeen < entries.length ? <p className="mt-5 text-xs text-muted-foreground">У части слов нет даты добавления; они включены в общий счётчик, но не в график.</p> : null}
          </>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value, detail }: { label: string; value: number; detail: string }) {
  return (
    <div className="rounded-[var(--radius)] border border-border bg-card p-5">
      <p className="text-xs text-muted-foreground">{label}</p>
      <strong className="mt-3 block font-serif text-4xl font-normal leading-none tabular-nums">{value.toLocaleString("ru-RU")}</strong>
      <p className="mt-2 text-xs text-muted-foreground">{detail}</p>
    </div>
  );
}
