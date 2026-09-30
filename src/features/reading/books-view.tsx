import { useMemo, useState } from "react";
import { ArrowRight, BookOpen, ImageDown, Loader2, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { BookOption, CoverSummary, LexemeRecord } from "@/types";
import { bookStats, formatDate, lookupsForBook, ruCount } from "./reading-domain";

export type BooksViewProps = {
  books: BookOption[];
  entries: LexemeRecord[];
  onOpenWord: (entry: LexemeRecord) => void;
  selectedBookKey?: string;
  onSelectBook?: (book: BookOption) => void;
  onDownloadCovers?: () => void;
  coversBusy?: boolean;
  coverSummary?: CoverSummary;
};

function BookCover({ title, author, coverDataUrl, compact = false }: { title: string; author: string; coverDataUrl?: string; compact?: boolean }) {
  return (
    <div
      aria-hidden="true"
      className={`relative flex shrink-0 flex-col justify-between overflow-hidden rounded-[var(--radius)] border border-primary/20 bg-primary p-3 text-primary-foreground shadow-sm ${compact ? "h-[86px] w-[62px]" : "h-[194px] w-[140px] p-5"}`}
    >
      {coverDataUrl ? <img src={coverDataUrl} alt="" className="absolute inset-0 h-full w-full object-cover" /> : <>
        <span className={`font-serif uppercase tracking-[0.19em] opacity-75 ${compact ? "text-[7px]" : "text-[9px]"}`}>Kindle Cards</span>
        <div>
          <p className={`font-serif leading-[1.1] ${compact ? "line-clamp-3 text-[11px]" : "line-clamp-4 text-[22px]"}`}>{title}</p>
          {author ? <p className={`mt-2 truncate opacity-75 ${compact ? "text-[7px]" : "text-[10px]"}`}>{author}</p> : null}
        </div>
        <span className="absolute -right-4 -top-4 h-12 w-12 rounded-full border border-current opacity-20" />
      </>}
    </div>
  );
}

export function BooksView({ books, entries, onOpenWord, selectedBookKey, onSelectBook, onDownloadCovers, coversBusy = false, coverSummary }: BooksViewProps) {
  const stats = useMemo(() => bookStats(books, entries), [books, entries]);
  const availableCovers = stats.filter((item) => item.book.cover_data_url).length;
  const [localBookKey, setLocalBookKey] = useState("");
  const [bookQuery, setBookQuery] = useState("");
  const [wordQuery, setWordQuery] = useState("");
  const [repeatedOnly, setRepeatedOnly] = useState(false);
  const activeKey = selectedBookKey ?? localBookKey;
  const activeBook = stats.find((item) => item.book.key === activeKey) ?? stats[0];
  const shownBooks = useMemo(() => {
    const query = bookQuery.trim().toLocaleLowerCase("ru");
    return query
      ? stats.filter((item) => `${item.book.label} ${item.author}`.toLocaleLowerCase("ru").includes(query))
      : stats;
  }, [bookQuery, stats]);
  const shownWords = useMemo(() => {
    if (!activeBook) return [];
    const query = wordQuery.trim().toLocaleLowerCase("ru");
    return activeBook.words
      .filter((entry) => {
        const occurrences = lookupsForBook(entry, activeBook.book.key);
        return (!repeatedOnly || occurrences.length > 1) &&
          (!query || [entry.lemma, entry.display_form, ...entry.forms].some((form) => form.toLocaleLowerCase("ru").includes(query)));
      })
      .sort((left, right) => {
        const leftLast = lookupsForBook(left, activeBook.book.key).reduce((last, item) => item.looked_up_at > last ? item.looked_up_at : last, "");
        const rightLast = lookupsForBook(right, activeBook.book.key).reduce((last, item) => item.looked_up_at > last ? item.looked_up_at : last, "");
        return rightLast.localeCompare(leftLast) || left.lemma.localeCompare(right.lemma);
      });
  }, [activeBook, repeatedOnly, wordQuery]);

  const selectBook = (book: BookOption) => {
    setLocalBookKey(book.key);
    setWordQuery("");
    setRepeatedOnly(false);
    onSelectBook?.(book);
  };

  return (
    <div className="app-scrollbar h-full overflow-y-auto bg-background px-5 py-6 text-foreground sm:px-8 lg:px-10">
      <div className="mx-auto max-w-[1440px]">
        <header className="mb-7 flex flex-wrap items-end justify-between gap-4 border-b border-border pb-6">
          <div>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-primary">Личная библиотека</p>
            <h1 className="font-serif text-4xl leading-tight tracking-tight sm:text-5xl">Книги и найденные слова</h1>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">История обращений к словарю Kindle, сгруппированная по книгам.</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-sm text-muted-foreground">{stats.length} {ruCount(stats.length, "книга", "книги", "книг")} · обложки {availableCovers}/{stats.length}</p>
            {onDownloadCovers && stats.length > 0 ? <Button type="button" size="sm" variant="secondary" onClick={onDownloadCovers} disabled={coversBusy} aria-busy={coversBusy}>
              {coversBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImageDown className="h-4 w-4" />}
              {coversBusy ? "Загружаем обложки" : "Загрузить обложки"}
            </Button> : null}
            {coverSummary?.errors ? <span role="status" className="text-xs text-destructive">Часть обложек не загрузилась: {coverSummary.errors}</span> : null}
          </div>
        </header>

        {stats.length === 0 ? (
          <div className="flex min-h-[320px] flex-col items-center justify-center rounded-[var(--radius)] border border-dashed border-border bg-card px-6 text-center">
            <BookOpen className="mb-4 h-9 w-9 text-primary" strokeWidth={1.5} />
            <h2 className="font-serif text-2xl">Здесь появятся ваши книги</h2>
            <p className="mt-2 max-w-md text-sm text-muted-foreground">После синхронизации Kindle книги и найденные в них слова появятся здесь.</p>
          </div>
        ) : (
          <div className="grid gap-7 lg:grid-cols-[280px,minmax(0,1fr)] xl:gap-9">
            <aside className="min-w-0">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="font-serif text-xl">Полка</h2>
                <span className="text-xs tabular-nums text-muted-foreground">{stats.length}</span>
              </div>
              <div className="relative mb-4">
                <Search aria-hidden="true" className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input aria-label="Поиск книги" value={bookQuery} onChange={(event) => setBookQuery(event.target.value)} placeholder="Найти книгу" className="pl-9" />
              </div>
              {shownBooks.length === 0 ? (
                <p className="rounded-[var(--radius)] border border-dashed border-border p-5 text-sm text-muted-foreground">По этому запросу книг нет.</p>
              ) : (
                <div className="space-y-1.5">
                  {shownBooks.map((item) => (
                    <button
                      key={item.book.key}
                      type="button"
                      onClick={() => selectBook(item.book)}
                      aria-current={activeBook?.book.key === item.book.key ? "true" : undefined}
                      className={`flex w-full items-center gap-3 rounded-[var(--radius)] border p-2 text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.99] ${activeBook?.book.key === item.book.key ? "border-primary/30 bg-primary/10" : "border-transparent hover:border-border hover:bg-secondary"}`}
                    >
                      <BookCover title={item.book.label} author={item.author} coverDataUrl={item.book.cover_data_url} compact />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-serif text-[15px] leading-tight">{item.book.label}</span>
                        <span className="mt-1 block truncate text-xs text-muted-foreground">{item.author || "Автор не указан"}</span>
                        <span className="mt-2 block text-[11px] tabular-nums text-muted-foreground">{item.wordCount} {ruCount(item.wordCount, "слово", "слова", "слов")} · {item.lookupCount} {ruCount(item.lookupCount, "обращение", "обращения", "обращений")}</span>
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </aside>

            {activeBook ? (
              <section className="min-w-0">
                <div className="flex flex-col gap-6 rounded-[var(--radius)] border border-border bg-card p-5 sm:flex-row sm:items-center sm:p-7">
                  <BookCover title={activeBook.book.label} author={activeBook.author} coverDataUrl={activeBook.book.cover_data_url} />
                  <div className="min-w-0 flex-1">
                    <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-primary">В этой книге</p>
                    <h2 className="font-serif text-3xl leading-tight sm:text-4xl">{activeBook.book.label}</h2>
                    <p className="mt-1 text-sm text-muted-foreground">{activeBook.author || "Автор не указан"}</p>
                    <div className="mt-6 grid grid-cols-2 gap-4 border-t border-border pt-5 sm:grid-cols-3">
                      <div><strong className="block font-serif text-3xl font-normal tabular-nums">{activeBook.wordCount}</strong><span className="text-xs text-muted-foreground">разных слов</span></div>
                      <div><strong className="block font-serif text-3xl font-normal tabular-nums">{activeBook.lookupCount}</strong><span className="text-xs text-muted-foreground">обращений</span></div>
                      <div><strong className="block font-serif text-3xl font-normal tabular-nums">{activeBook.repeatedWordCount}</strong><span className="text-xs text-muted-foreground">слов искали повторно</span></div>
                    </div>
                    {activeBook.lastLookupAt ? <p className="mt-5 text-xs text-muted-foreground">Последнее обращение: {formatDate(activeBook.lastLookupAt)}</p> : null}
                  </div>
                </div>

                <div className="mt-7 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="font-serif text-2xl">Слова из книги</h3>
                    <p className="mt-1 text-xs text-muted-foreground">Откройте слово, чтобы увидеть его контекст и обработку.</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button type="button" size="sm" variant={repeatedOnly ? "default" : "secondary"} aria-pressed={repeatedOnly} onClick={() => setRepeatedOnly((value) => !value)}>Повторные · {activeBook.repeatedWordCount}</Button>
                    <div className="relative w-40 sm:w-48">
                      <Search aria-hidden="true" className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                      <Input aria-label="Поиск слова в книге" value={wordQuery} onChange={(event) => setWordQuery(event.target.value)} placeholder="Найти слово" className="h-8 pl-8 pr-8 text-xs" />
                      {wordQuery ? <button type="button" aria-label="Очистить поиск" onClick={() => setWordQuery("")} className="absolute right-2 top-1/2 -translate-y-1/2 rounded text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><X className="h-3.5 w-3.5" /></button> : null}
                    </div>
                  </div>
                </div>

                <div className="mt-4 overflow-hidden rounded-[var(--radius)] border border-border bg-card">
                  {shownWords.length === 0 ? (
                    <p className="px-6 py-12 text-center text-sm text-muted-foreground">
                      {activeBook.wordCount === 0 ? "По этой книге пока нет обращений к словарю." : "Слова по выбранному фильтру не найдены."}
                    </p>
                  ) : shownWords.map((entry) => {
                    const occurrences = lookupsForBook(entry, activeBook.book.key);
                    const context = occurrences.find((item) => item.context)?.context;
                    return (
                      <button
                        key={entry.id}
                        type="button"
                        onClick={() => onOpenWord(entry)}
                        className="group flex w-full items-center gap-3 border-b border-border px-4 py-3 text-left transition-colors last:border-b-0 hover:bg-secondary focus-visible:relative focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:bg-primary/10 sm:px-5"
                      >
                        <span className="min-w-0 flex-1 sm:grid sm:grid-cols-[minmax(120px,0.8fr),minmax(0,1.4fr)] sm:items-center sm:gap-5">
                          <span className="block truncate font-serif text-lg leading-tight">{entry.display_form || entry.lemma}</span>
                          <span className="mt-1 block truncate text-xs italic text-muted-foreground sm:mt-0">{context || "Контекст не сохранён"}</span>
                        </span>
                        <span className="shrink-0 text-right text-[11px] tabular-nums text-muted-foreground">{occurrences.length} {ruCount(occurrences.length, "обращение", "обращения", "обращений")}</span>
                        <ArrowRight aria-hidden="true" className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
                      </button>
                    );
                  })}
                </div>
              </section>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
