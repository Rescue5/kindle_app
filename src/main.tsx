import * as React from "react";
import ReactDOM from "react-dom/client";
import { BarChart3, BookOpen, Home, Library, RotateCcw, Settings } from "lucide-react";
import { SettingsView } from "@/components/settings-view";
import { LibraryWorkspace } from "@/features/library/library-workspace";
import { useLibraryController } from "@/features/library/use-library-controller";
import { BooksView } from "@/features/reading/books-view";
import { InsightsView } from "@/features/reading/insights-view";
import { ReadingHome } from "@/features/reading/reading-home";
import { ReviewView } from "@/features/reading/review-view";
import { callBackend } from "@/lib/backend";
import type { LexemeRecord } from "@/types";
import "@/index.css";
import "@/features/reading/reading.css";

type View = "home" | "books" | "words" | "review" | "insights" | "settings";

const navigation = [
  { label: "Главная", icon: Home, view: "home" as const },
  { label: "Книги", icon: BookOpen, view: "books" as const },
  { label: "Слова", icon: Library, view: "words" as const },
  { label: "Повторение", icon: RotateCcw, view: "review" as const },
  { label: "Аналитика", icon: BarChart3, view: "insights" as const },
  { label: "Настройки", icon: Settings, view: "settings" as const },
];

function App() {
  const controller = useLibraryController();
  const [view, setView] = React.useState<View>("home");
  const [dueCount, setDueCount] = React.useState(0);

  React.useEffect(() => {
    let active = true;
    void callBackend<{ due_count: number }>("load_review", { limit: 1 })
      .then((result) => { if (active) setDueCount(result.due_count); })
      .catch(() => { if (active) setDueCount(0); });
    return () => { active = false; };
  }, [controller.entries]);

  function openWord(entry?: LexemeRecord | string) {
    controller.setQuery("");
    controller.setSelectedBookKey("");
    controller.setQuickFilter("all");
    if (entry) controller.setSelectedId(typeof entry === "string" ? entry : entry.id);
    setView("words");
  }

  function openNewWords() {
    controller.setQuery("");
    controller.setSelectedBookKey("");
    controller.setQuickFilter("new");
    setView("words");
  }

  const busy = controller.operation.status === "running";
  const status = busy
    ? controller.operation.message || controller.operation.title
    : controller.operation.status === "error"
      ? controller.operation.error || controller.operation.message || controller.operation.title
      : controller.operation.kind === "covers" && controller.operation.status === "completed"
        ? controller.operation.message
      : controller.queueStatus.total > 0
        ? `Обработка: ${controller.queueStatus.total} слов`
        : "Библиотека готова";

  return (
    <div className="reading-app">
      <aside className="reading-sidebar">
        <button type="button" className="reading-brand" onClick={() => setView("home")} aria-label="Kindle Cards — главная">
          <span className="reading-brand-mark"><BookOpen size={23} strokeWidth={1.8} /></span>
          <span><strong>Kindle Cards</strong><small>Слова из вашего чтения</small></span>
        </button>
        <nav className="reading-nav" aria-label="Основная навигация">
          {navigation.map((item) => {
            const Icon = item.icon;
            return <button key={item.view} type="button" onClick={() => setView(item.view)} aria-current={view === item.view ? "page" : undefined} className={view === item.view ? "is-active" : ""}><Icon size={18} strokeWidth={1.8} /><span>{item.label}</span>{item.view === "review" && dueCount > 0 ? <em>{dueCount}</em> : null}</button>;
          })}
        </nav>
        <div className="reading-sidebar-bottom"><span>В библиотеке</span><strong>{controller.entries.length} слов</strong></div>
      </aside>

      <div className="reading-app-main">
        <div className="reading-view-frame">
          {view === "home" ? <ReadingHome bookOptions={controller.books} entries={controller.entries} connectors={controller.connectors} operation={controller.operation} queueStatus={controller.queueStatus} dueCount={dueCount} onSync={() => void controller.syncKindle()} onReview={() => setView("review")} onBooks={() => setView("books")} onWords={openWord} onNewWords={openNewWords} /> : null}
          {view === "books" ? <BooksView books={controller.books} entries={controller.entries} onOpenWord={openWord} onDownloadCovers={controller.downloadCovers} coversBusy={controller.coversBusy || controller.operation.status === "running"} coverSummary={controller.coverSummary} /> : null}
          {view === "words" ? <LibraryWorkspace controller={controller} /> : null}
          {view === "review" ? <ReviewView onCountsChange={setDueCount} onOpenWords={() => openWord()} /> : null}
          {view === "insights" ? <InsightsView books={controller.books} entries={controller.entries} onOpenWord={openWord} /> : null}
          {view === "settings" ? <SettingsView settings={controller.settings} onChange={controller.setSettings} /> : null}
        </div>
        <div className="reading-status" role="status"><span className={busy ? "reading-status-dot is-busy" : "reading-status-dot"} />{status}{controller.operation.status === "error" ? <button type="button" onClick={controller.retry}>Повторить</button> : null}</div>
      </div>
    </div>
  );
}

const rootElement = document.getElementById("root")!;
const rootState = rootElement as typeof rootElement & { __kindleCardsRoot?: ReturnType<typeof ReactDOM.createRoot> };
rootState.__kindleCardsRoot ??= ReactDOM.createRoot(rootElement);
rootState.__kindleCardsRoot.render(<React.StrictMode><App /></React.StrictMode>);
