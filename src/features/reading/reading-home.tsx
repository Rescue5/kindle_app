import * as React from "react";
import { ArrowRight, BookOpen, ChevronRight, RefreshCw, RotateCcw } from "lucide-react";
import type { BookOption, ConnectorStatus, LexemeRecord, Operation, QueueStatus } from "@/types";
import { ruCount } from "./reading-domain";

type Props = {
  bookOptions: BookOption[];
  entries: LexemeRecord[];
  connectors: ConnectorStatus;
  operation: Operation;
  queueStatus: QueueStatus;
  dueCount: number;
  onSync: () => void;
  onReview: () => void;
  onBooks: () => void;
  onWords: (id?: string) => void;
  onNewWords: () => void;
};

type BookSummary = { key: string; title: string; author: string; coverDataUrl?: string; lookups: number; words: number; latest: number };

function timestamp(value: string) {
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function summarizeBooks(entries: LexemeRecord[], bookOptions: BookOption[]): BookSummary[] {
  const map = new Map<string, BookSummary>();
  const coverByKey = new Map(bookOptions.map((book) => [book.key, book.cover_data_url]));
  const titleByKey = new Map(bookOptions.map((book) => [book.key, book.display_title]));
  for (const entry of entries) {
    const seen = new Set<string>();
    for (const occurrence of entry.occurrences) {
      const key = occurrence.book_key || occurrence.book_title;
      if (!key) continue;
      const book = map.get(key) ?? { key, title: titleByKey.get(key) || occurrence.book_title || key, author: occurrence.authors, coverDataUrl: coverByKey.get(key), lookups: 0, words: 0, latest: 0 };
      book.lookups += 1;
      if (!seen.has(key)) book.words += 1;
      book.latest = Math.max(book.latest, timestamp(occurrence.looked_up_at));
      map.set(key, book);
      seen.add(key);
    }
  }
  return [...map.values()].sort((a, b) => b.latest - a.latest || b.lookups - a.lookups);
}

function BookJacket({ book, index }: { book: BookSummary; index: number }) {
  return (
    <div className={`reading-jacket reading-jacket-${index % 4}${book.coverDataUrl ? " is-real-cover" : ""}`} aria-hidden="true">
      {book.coverDataUrl ? <img className="reading-jacket-image" src={book.coverDataUrl} alt="" /> : <><span className="reading-jacket-rule" /><span className="reading-jacket-title">{book.title}</span><span className="reading-jacket-author">{book.author || "Из библиотеки Kindle"}</span></>}
    </div>
  );
}

export function ReadingHome({ bookOptions, entries, connectors, operation, queueStatus, dueCount, onSync, onReview, onBooks, onWords, onNewWords }: Props) {
  const books = React.useMemo(() => summarizeBooks(entries, bookOptions), [entries, bookOptions]);
  const recent = React.useMemo(() => [...entries].sort((a, b) => timestamp(b.last_seen_at) - timestamp(a.last_seen_at)).slice(0, 5), [entries]);
  const latestBook = books[0];
  const freshCount = React.useMemo(() => entries.filter((entry) => entry.freshness === "new").length, [entries]);
  const readyCount = React.useMemo(() => entries.filter((entry) => entry.processing.state === "ready" && entry.processing.analysis?.accepted).length, [entries]);
  const busy = operation.status === "running";

  return (
    <main className="reading-page app-scrollbar">
      <div className="reading-page-inner">
        <div className="reading-intro">
          <div>
            <h1 className="reading-display reading-page-title">Продолжайте читать</h1>
            <p className="reading-lede">Слова из книг постепенно становятся вашим словарём.</p>
          </div>
          <div className="reading-intro-count"><strong>{entries.length}</strong><span>слов в библиотеке</span></div>
        </div>

        <section className="reading-feature" aria-label="Последняя книга">
          {latestBook ? (
            <>
              <BookJacket book={latestBook} index={0} />
              <div className="reading-feature-content">
                <span className="reading-eyebrow">Последняя книга в Kindle</span>
                <h2 className="reading-display">{latestBook.title}</h2>
                {latestBook.author ? <p className="reading-feature-author">{latestBook.author}</p> : null}
                <p className="reading-feature-description">Ваши находки из этой книги уже собраны в библиотеке.</p>
                <div className="reading-feature-metrics">
                  <div><strong>{latestBook.words}</strong><span>уникальных слов</span></div>
                  <div><strong>{latestBook.lookups}</strong><span>просмотров в Kindle</span></div>
                  <div><strong>{freshCount}</strong><span>новых в библиотеке</span></div>
                </div>
                <div className="reading-feature-actions">
                  <button className="reading-primary-button" type="button" onClick={onSync} disabled={busy || connectors.kindle.state !== "connected"}>
                    <RefreshCw size={16} className={busy && operation.kind === "kindle" ? "animate-spin" : ""} />
                    Синхронизировать Kindle
                  </button>
                  <button className="reading-text-button" type="button" onClick={onBooks}>Открыть книги <ArrowRight size={16} /></button>
                  {freshCount > 0 ? <button className="reading-text-button" type="button" onClick={onNewWords}>Разобрать новые <ArrowRight size={16} /></button> : null}
                </div>
                {connectors.kindle.state !== "connected" ? <p className="reading-help">Подключите Kindle по USB для новой синхронизации.</p> : null}
              </div>
            </>
          ) : (
            <div className="reading-empty-feature">
              <BookOpen size={32} />
              <h2 className="reading-display">Ваша история чтения начинается здесь</h2>
              <p>Подключите Kindle, чтобы увидеть книги и найденные в них слова.</p>
              <button className="reading-primary-button" type="button" onClick={onSync} disabled={busy}>Проверить Kindle</button>
            </div>
          )}
        </section>

        <div className="reading-home-columns">
          <section className="reading-recent">
            <div className="reading-section-heading"><h2 className="reading-display">Недавние слова</h2><button type="button" className="reading-text-button" onClick={() => onWords()}>Все слова <ArrowRight size={16} /></button></div>
            {recent.length ? <div className="reading-word-list">{recent.map((entry) => {
              const occurrence = entry.occurrences[0];
              return <button key={entry.id} type="button" className="reading-word-row" onClick={() => onWords(entry.id)}>
                <span className="reading-word-title">{entry.lemma}</span>
                <span className="reading-word-context">{occurrence?.context || entry.processing.analysis?.russian_meanings || "Контекст пока не найден"}</span>
                <span className="reading-word-book">{occurrence?.book_title || "Без книги"}</span>
                <ChevronRight size={16} />
              </button>;
            })}</div> : <p className="reading-empty-inline">После первой синхронизации здесь появятся слова из ваших книг.</p>}
          </section>

          <aside className="reading-home-side">
            <section className="reading-review-invite">
              <RotateCcw size={20} />
              <h2 className="reading-display">Пора повторить</h2>
              <p>{dueCount > 0 ? `${dueCount} ${ruCount(dueCount, "слово", "слова", "слов")} ${dueCount === 1 ? "ждёт" : "ждут"} вас сегодня.` : "На сегодня всё повторено. Новые карточки появятся из обработанных слов."}</p>
              <button className="reading-secondary-button" type="button" onClick={onReview}>Открыть повторение <ArrowRight size={16} /></button>
            </section>
            <section className="reading-library-glance">
              <div className="reading-section-heading"><h2 className="reading-display">Ваша библиотека</h2><button className="reading-text-button" type="button" onClick={onBooks}>Все книги <ArrowRight size={16} /></button></div>
              <div className="reading-library-covers">{books.slice(0, 3).map((book, index) => <button key={book.key} type="button" onClick={onBooks} title={book.title}><BookJacket book={book} index={index + 1} /><span>{book.title}</span></button>)}</div>
              <p className="reading-library-summary">{books.length} {ruCount(books.length, "книга", "книги", "книг")} · {readyCount} {ruCount(readyCount, "обработанное слово", "обработанных слова", "обработанных слов")}</p>
            </section>
          </aside>
        </div>
        {queueStatus.total > 0 ? <p className="reading-queue-note">Обрабатывается в фоне: {queueStatus.total} слов</p> : null}
      </div>
    </main>
  );
}
