import * as React from "react";
import { ArrowLeft, ArrowRight, BookOpen, Check, RotateCcw } from "lucide-react";
import { callBackend } from "@/lib/backend";
import type { LexemeOccurrence, WordAnalysis } from "@/types";
import { ruCount } from "./reading-domain";

type ReviewCard = {
  lexeme_id: string;
  lemma: string;
  display_form: string;
  analysis?: WordAnalysis | null;
  occurrences: LexemeOccurrence[];
  review: { due_at: string; interval_days: number; repetitions: number; last_rating: string; reviewed_at: string };
};

type ReviewResult = { cards: ReviewCard[]; due_count: number; total_count: number };
type Rating = "again" | "hard" | "good";

function cloze(card: ReviewCard) {
  const context = card.occurrences.find((item) => item.context)?.context ?? "";
  if (!context) return "";
  const word = card.occurrences.find((item) => item.context)?.word || card.display_form || card.lemma;
  const position = context.toLocaleLowerCase().indexOf(word.toLocaleLowerCase());
  if (position < 0) return context;
  return `${context.slice(0, position)}______${context.slice(position + word.length)}`;
}

export function ReviewView({ onCountsChange, onOpenWords }: { onCountsChange: (due: number) => void; onOpenWords: () => void }) {
  const [result, setResult] = React.useState<ReviewResult | null>(null);
  const [revealed, setRevealed] = React.useState(false);
  const [working, setWorking] = React.useState(false);
  const [error, setError] = React.useState("");
  const [completed, setCompleted] = React.useState(0);

  const refresh = React.useCallback(async () => {
    const next = await callBackend<ReviewResult>("load_review", { limit: 20 });
    setResult(next);
    onCountsChange(next.due_count);
    setRevealed(false);
  }, [onCountsChange]);

  React.useEffect(() => {
    let mounted = true;
    void callBackend<ReviewResult>("load_review", { limit: 20 })
      .then((next) => { if (mounted) { setResult(next); onCountsChange(next.due_count); } })
      .catch((cause) => { if (mounted) setError(String(cause)); });
    return () => { mounted = false; };
  }, [onCountsChange]);

  const card = result?.cards[0];
  async function rate(rating: Rating) {
    if (!card || working) return;
    setWorking(true);
    setError("");
    try {
      await callBackend("rate_review", { lexeme_id: card.lexeme_id, rating });
      setCompleted((count) => count + 1);
      await refresh();
    } catch (cause) {
      setError(String(cause));
    } finally {
      setWorking(false);
    }
  }

  return (
    <main className="reading-page app-scrollbar">
      <div className="reading-page-inner reading-review-page">
        <header className="reading-page-header">
          <div><h1 className="reading-display reading-page-title">Повторение</h1><p className="reading-lede">Слова, которые встретились вам во время чтения.</p></div>
          {result ? <span className="reading-count">{result.due_count} сейчас · {result.total_count} в колоде</span> : null}
        </header>

        {error ? <div className="reading-error" role="alert">{error}<button type="button" onClick={() => void refresh()}>Повторить запрос</button></div> : null}
        {!result && !error ? <div className="reading-loading">Загружаем карточки…</div> : null}
        {result && !card ? <div className="reading-review-complete"><div className="reading-complete-icon"><Check size={27} /></div><h2 className="reading-display">На сегодня всё</h2><p>{completed ? `Вы повторили ${completed} ${ruCount(completed, "слово", "слова", "слов")}. Хорошая работа.` : "Сейчас нет слов для повторения. Обработанные слова появятся здесь в своё время."}</p><button type="button" className="reading-primary-button" onClick={onOpenWords}>Открыть слова <ArrowRight size={16} /></button></div> : null}

        {card ? <div className="reading-review-stage">
          <div className="reading-review-progress"><span>Карточка {completed + 1}</span><span>{result?.due_count ?? 0} осталось</span></div>
          <article className="reading-flashcard">
            <div className="reading-flashcard-top"><span>Слово из вашей библиотеки</span><RotateCcw size={17} /></div>
            <h2 className="reading-display">{card.lemma}</h2>
            {cloze(card) ? <blockquote>{cloze(card)}</blockquote> : <p className="reading-flashcard-empty">Контекст из Kindle не найден.</p>}
            {card.occurrences[0]?.book_title ? <div className="reading-flashcard-source"><BookOpen size={14} />{card.occurrences[0].book_title}</div> : null}
            {revealed ? <div className="reading-flashcard-answer"><span>Ответ</span><strong>{card.analysis?.russian_meanings || card.display_form}</strong>{!card.analysis?.russian_meanings ? <p>Перевод пока не добавлен; сравните слово с контекстом выше.</p> : null}{card.occurrences[0]?.context ? <p>{card.occurrences[0].context}</p> : null}</div> : <button type="button" className="reading-primary-button" onClick={() => setRevealed(true)}>Показать ответ <ArrowRight size={16} /></button>}
          </article>
          {revealed ? <div className="reading-review-ratings"><button type="button" disabled={working} onClick={() => void rate("again")}>Не знаю <span>Скоро снова</span></button><button type="button" disabled={working} onClick={() => void rate("hard")}>Трудно <span>Повторить раньше</span></button><button type="button" disabled={working} onClick={() => void rate("good")}>Знаю <span>Отложить</span></button></div> : <div className="reading-review-tip"><ArrowLeft size={15} /> Сначала вспомните значение слова</div>}
        </div> : null}
      </div>
    </main>
  );
}
