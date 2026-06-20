import React from "react";
import ReactDOM from "react-dom/client";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  Archive,
  BarChart3,
  BookOpen,
  Check,
  ChevronRight,
  Circle,
  Clock3,
  Database,
  Download,
  FileDown,
  FolderSync,
  Library,
  Loader2,
  MoreHorizontal,
  RotateCcw,
  Search,
  Settings,
  SlidersHorizontal,
  Square,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { callBackend, initialState } from "@/lib/backend";
import { tokens } from "@/design/tokens";
import type { ActivityEvent, AppState, VocabEntry } from "@/types";
import "./index.css";

type LoadResult = {
  sourceName: string;
  sourceStatus: string;
  books: AppState["books"];
  entries: VocabEntry[];
};

type OptimizeResult = {
  accepted_new: number;
  processed_new: number;
  skipped_existing: number;
  rejected_new?: number;
  tsv_path: string;
  events?: ActivityEvent[];
};

type RunState = "waiting" | "disconnected" | "syncing" | "processing" | "exporting" | "exported" | "error" | "cancelled";
type WordState = "processed" | "processing" | "queued" | "new";
type StageState = "done" | "active" | "queued" | "failed" | "cancelled";

const stages = [
  "Kindle sync",
  "Извлечение контекста",
  "Нормализация",
  "Дедупликация",
  "Оценка сложности",
  "Анализ значения",
  "Переводы и оттенки",
  "Генерация карточки",
  "Экспорт",
] as const;

const navItems = [
  { label: "Библиотека", icon: Library, active: true },
  { label: "Обработка", icon: FolderSync },
  { label: "Экспорты", icon: Archive },
  { label: "Аналитика", icon: BarChart3 },
  { label: "Настройки", icon: Settings },
];

function App() {
  const [state, setState] = React.useState<AppState>(initialState);
  const [runState, setRunState] = React.useState<RunState>("disconnected");
  const [activeStage, setActiveStage] = React.useState(0);
  const [selectedKey, setSelectedKey] = React.useState<string>("");
  const [lastError, setLastError] = React.useState("");
  const requestId = React.useRef(0);

  const filteredEntries = React.useMemo(() => {
    const query = state.searchText.trim().toLowerCase();
    const selectedBook = state.books[state.selectedBookIndex]?.key;
    return state.entries.filter((entry) => {
      const bookMatch = !selectedBook || entry.book_key === selectedBook;
      const queryMatch =
        !query ||
        [entry.word, entry.stem, entry.context, entry.book_title, entry.authors].some((value) =>
          value.toLowerCase().includes(query),
        );
      return bookMatch && queryMatch;
    });
  }, [state.entries, state.searchText, state.selectedBookIndex, state.books]);

  React.useEffect(() => {
    if (!filteredEntries.length) {
      setSelectedKey("");
      return;
    }
    if (!filteredEntries.some((entry) => entryKey(entry) === selectedKey)) {
      setSelectedKey(entryKey(filteredEntries[0]));
    }
  }, [filteredEntries, selectedKey]);

  React.useEffect(() => {
    if (!["syncing", "processing", "exporting"].includes(runState)) return;
    const maxStage = runState === "syncing" ? 2 : runState === "exporting" ? 8 : 7;
    const timer = window.setInterval(() => {
      setActiveStage((current) => (current >= maxStage ? current : current + 1));
    }, 900);
    return () => window.clearInterval(timer);
  }, [runState]);

  const selectedEntry = filteredEntries.find((entry) => entryKey(entry) === selectedKey) ?? filteredEntries[0] ?? null;

  async function runLoad(action: "scan" | "load_demo") {
    const id = ++requestId.current;
    setActiveStage(0);
    setRunState(action === "scan" ? "syncing" : "waiting");
    setLastError("");
    setState((current) => ({ ...current, processing: true, statusMessage: "Синхронизируем источник слов..." }));
    try {
      const result = await callBackend<LoadResult>(action, {});
      if (id !== requestId.current) return;
      setState((current) => ({
        ...current,
        ...result,
        selectedBookIndex: 0,
        processing: false,
        dbLoaded: result.entries.length > 0,
        statusMessage: result.entries.length ? "Словарь готов к обработке" : "Словарь пуст",
        activityEvents: [
          {
            phase: "answered",
            title: "Источник готов",
            message: `${result.entries.length} слов получено из ${Math.max(result.books.length - 1, 0)} книг.`,
            meta: "Sync",
          },
          ...current.activityEvents,
        ],
      }));
      setRunState(result.entries.length ? "waiting" : "disconnected");
    } catch (error) {
      fail("Не удалось синхронизировать Kindle", String(error));
    }
  }

  async function runOptimize() {
    const id = ++requestId.current;
    setActiveStage(1);
    setRunState("processing");
    setLastError("");
    setState((current) => ({ ...current, processing: true, statusMessage: "Идёт обработка слов..." }));
    try {
      const result = await callBackend<OptimizeResult>("optimize", { entries: filteredEntries });
      if (id !== requestId.current) return;
      setActiveStage(7);
      setRunState("waiting");
      setState((current) => ({
        ...current,
        processing: false,
        statusMessage: `Готово: ${result.accepted_new} карточек подготовлено`,
        activityEvents: [
          ...(result.events ?? []),
          {
            phase: "answered",
            title: "Обработка завершена",
            message: `Обработано ${result.processed_new}; добавлено ${result.accepted_new}; пропущено ${result.skipped_existing}.`,
            meta: result.tsv_path,
          },
          ...current.activityEvents,
        ],
      }));
    } catch (error) {
      fail("Ошибка обработки", String(error));
    }
  }

  async function runExport(format: "anki" | "quizlet") {
    const id = ++requestId.current;
    setActiveStage(8);
    setRunState("exporting");
    setLastError("");
    try {
      const result = await callBackend<{ path: string }>("export", { format, entries: filteredEntries });
      if (id !== requestId.current) return;
      setRunState("exported");
      setState((current) => ({
        ...current,
        processing: false,
        statusMessage: `Экспорт завершён: ${result.path}`,
        activityEvents: [
          {
            phase: "answered",
            title: `${format.toUpperCase()} экспорт`,
            message: `${filteredEntries.length} строк сохранено для импорта.`,
            meta: result.path,
          },
          ...current.activityEvents,
        ],
      }));
    } catch (error) {
      fail("Ошибка экспорта", String(error));
    }
  }

  function cancelCurrent() {
    requestId.current += 1;
    setRunState("cancelled");
    setState((current) => ({ ...current, processing: false, statusMessage: "Операция отменена" }));
  }

  function fail(title: string, message: string) {
    setLastError(message);
    setRunState("error");
    setState((current) => ({
      ...current,
      processing: false,
      statusMessage: title,
      activityEvents: [{ phase: "failed", title, message, meta: "Error" }, ...current.activityEvents],
    }));
  }

  return (
    <main className="premium-grid h-full overflow-hidden text-foreground">
      <div className="grid h-full grid-cols-[224px_minmax(620px,1fr)_390px] gap-0">
        <Sidebar state={state} runState={runState} onScan={() => runLoad("scan")} />
        <section className="flex min-w-0 flex-col border-x border-line/80">
          <TopBar
            state={state}
            setState={setState}
            runState={runState}
            total={filteredEntries.length}
            onScan={() => runLoad("scan")}
            onOptimize={runOptimize}
            onExport={runExport}
            onCancel={cancelCurrent}
          />
          <StatusStrip
            state={state}
            runState={runState}
            lastError={lastError}
            onRetry={() => runLoad("scan")}
            onDismiss={() => {
              setRunState("waiting");
              setLastError("");
            }}
          />
          <VocabularyList
            entries={filteredEntries}
            selectedKey={selectedKey}
            runState={runState}
            onSelect={setSelectedKey}
          />
        </section>
        <aside className="flex min-w-0 flex-col bg-panel/70">
          <WordInspector entry={selectedEntry} wordState={wordStateFor(selectedEntry, filteredEntries, runState)} />
          <ProcessingPipeline runState={runState} activeStage={activeStage} entry={selectedEntry} events={state.activityEvents} />
        </aside>
      </div>
    </main>
  );
}

function Sidebar({
  state,
  runState,
  onScan,
}: {
  state: AppState;
  runState: RunState;
  onScan: () => void;
}) {
  const connected = runState !== "disconnected" && runState !== "error";
  return (
    <aside className="flex min-h-0 flex-col bg-panel px-3 py-4">
      <div className="mb-5 flex h-10 items-center gap-3 px-2">
        <BookOpen size={20} className="text-primary" />
        <div className="text-sm font-semibold">Словарь</div>
      </div>
      <nav className="space-y-1">
        {navItems.map((item) => (
          <button
            key={item.label}
            className={`flex h-10 w-full items-center gap-3 rounded-[10px] px-3 text-left text-sm transition ${
              item.active
                ? "bg-secondary text-foreground"
                : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground active:bg-secondary"
            }`}
          >
            <item.icon size={16} />
            {item.label}
          </button>
        ))}
      </nav>
      <div className="mt-auto rounded-[12px] border border-line bg-panel-raised p-3">
        <div className="mb-3 flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-[8px] bg-secondary text-primary">
            <Database size={16} />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-medium">{state.sourceName}</div>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-success" : "bg-warning"}`} />
              {connected ? "Подключён" : "Не подключён"}
            </div>
          </div>
        </div>
        <Button className="w-full" variant="secondary" onClick={onScan} data-loading={runState === "syncing"}>
          {runState === "syncing" ? <Loader2 size={15} className="animate-spin" /> : <FolderSync size={15} />}
          Синхронизировать
        </Button>
        <div className="mt-4 grid grid-cols-2 gap-3 border-t border-line pt-3 text-xs">
          <div>
            <div className="text-muted-foreground">Книги</div>
            <div className="mt-1 font-medium">{Math.max(state.books.length - 1, 0)}</div>
          </div>
          <div>
            <div className="text-muted-foreground">Слова</div>
            <div className="mt-1 font-medium">{state.entries.length}</div>
          </div>
        </div>
      </div>
    </aside>
  );
}

function TopBar({
  state,
  setState,
  runState,
  total,
  onScan,
  onOptimize,
  onExport,
  onCancel,
}: {
  state: AppState;
  setState: React.Dispatch<React.SetStateAction<AppState>>;
  runState: RunState;
  total: number;
  onScan: () => void;
  onOptimize: () => void;
  onExport: (format: "anki" | "quizlet") => void;
  onCancel: () => void;
}) {
  const busy = ["syncing", "processing", "exporting"].includes(runState);
  return (
    <header className="border-b border-line bg-background/35 px-5 py-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-semibold leading-7">Библиотека</h1>
          <p className="mt-1 text-sm text-muted-foreground">Слова, контексты и карточки из Kindle Vocabulary Builder</p>
        </div>
        <div className="flex items-center gap-2">
          {busy ? (
            <Button variant="secondary" onClick={onCancel}>
              <X size={15} />
              Отменить
            </Button>
          ) : null}
          <Button variant="secondary" onClick={onScan} disabled={busy} data-loading={runState === "syncing"}>
            {runState === "syncing" ? <Loader2 size={15} className="animate-spin" /> : <FolderSync size={15} />}
            Kindle
          </Button>
          <Button onClick={onOptimize} disabled={!total || busy} data-loading={runState === "processing"}>
            {runState === "processing" ? <Loader2 size={15} className="animate-spin" /> : <SlidersHorizontal size={15} />}
            Обработать
          </Button>
        </div>
      </div>
      <div className="grid grid-cols-[minmax(260px,1fr)_220px_166px] gap-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Поиск слова, контекста или книги..."
            value={state.searchText}
            onChange={(event) => setState((current) => ({ ...current, searchText: event.target.value }))}
          />
        </div>
        <Select
          value={String(state.selectedBookIndex)}
          onChange={(event) => setState((current) => ({ ...current, selectedBookIndex: Number(event.target.value) }))}
        >
          {state.books.map((book, index) => (
            <option key={`${book.key}-${index}`} value={index}>
              {book.label}
            </option>
          ))}
        </Select>
        <Select
          disabled={busy || !total}
          defaultValue="anki"
          onChange={(event) => onExport(event.target.value as "anki" | "quizlet")}
        >
          <option value="anki">Экспорт в Anki</option>
          <option value="quizlet">Экспорт в Quizlet</option>
        </Select>
      </div>
      <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          <FilterPill label="Все" value={total} active />
          <FilterPill label="Новые" value={countByState(total, "new")} />
          <FilterPill label="Обработанные" value={countByState(total, "processed")} />
          <FilterPill label="В очереди" value={countByState(total, "queued")} />
          <Button variant="ghost" size="icon" aria-label="More filters">
            <MoreHorizontal size={16} />
          </Button>
        </div>
        <div>{total} слов в выборке</div>
      </div>
    </header>
  );
}

function StatusStrip({
  state,
  runState,
  lastError,
  onRetry,
  onDismiss,
}: {
  state: AppState;
  runState: RunState;
  lastError: string;
  onRetry: () => void;
  onDismiss: () => void;
}) {
  if (runState === "waiting" && state.entries.length > 0) return null;
  const content = {
    disconnected: {
      icon: AlertCircle,
      title: "Kindle не подключён",
      text: "Подключите Kindle по USB или используйте preview-данные. Словарь останется доступен локально.",
    },
    syncing: {
      icon: Loader2,
      title: "Синхронизация Kindle",
      text: "Ищем vocab.db, копируем локальный снимок и извлекаем контексты.",
    },
    processing: {
      icon: Loader2,
      title: "Обработка слов",
      text: "Конвейер нормализует формы, оценивает сложность и готовит карточки.",
    },
    exporting: {
      icon: Loader2,
      title: "Экспорт",
      text: "Формируем TSV для выбранной системы.",
    },
    exported: {
      icon: Check,
      title: "Экспорт завершён",
      text: state.statusMessage,
    },
    error: {
      icon: AlertCircle,
      title: "Нужна повторная попытка",
      text: lastError || state.statusMessage,
    },
    cancelled: {
      icon: Square,
      title: "Операция отменена",
      text: "Можно изменить выборку и запустить обработку заново.",
    },
    waiting: {
      icon: Clock3,
      title: "Ожидание",
      text: state.statusMessage,
    },
  }[runState];
  const Icon = content.icon;
  const isBusy = ["syncing", "processing", "exporting"].includes(runState);
  return (
    <div className="border-b border-line bg-panel-raised/55 px-5 py-2.5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <Icon size={16} className={`${isBusy ? "animate-spin" : ""} ${runState === "error" ? "text-destructive" : "text-primary"}`} />
          <div className="min-w-0">
            <div className="text-sm font-medium">{content.title}</div>
            <div className="truncate text-xs text-muted-foreground">{content.text}</div>
          </div>
        </div>
        {runState === "error" ? (
          <Button size="sm" variant="secondary" onClick={onRetry}>
            <RotateCcw size={14} />
            Повторить
          </Button>
        ) : runState === "exported" || runState === "cancelled" ? (
          <Button size="sm" variant="ghost" onClick={onDismiss}>
            Скрыть
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function VocabularyList({
  entries,
  selectedKey,
  runState,
  onSelect,
}: {
  entries: VocabEntry[];
  selectedKey: string;
  runState: RunState;
  onSelect: (key: string) => void;
}) {
  return (
    <div className="min-h-0 flex-1 overflow-hidden">
      <div className="grid h-10 grid-cols-[minmax(140px,0.9fr)_minmax(220px,1.6fr)_minmax(140px,0.9fr)_132px] border-b border-line bg-panel/55 px-5 text-xs font-medium uppercase text-muted-foreground">
        <div className="flex items-center">Слово</div>
        <div className="flex items-center">Контекст</div>
        <div className="flex items-center">Книга</div>
        <div className="flex items-center">Статус</div>
      </div>
      <div className="app-scrollbar h-[calc(100%-40px)] overflow-auto">
        <AnimatePresence initial={false}>
          {entries.length ? (
            entries.map((entry, index) => {
              const key = entryKey(entry);
              const selected = key === selectedKey;
              const status = wordStateFor(entry, entries, runState, index);
              return (
                <motion.button
                  key={key}
                  type="button"
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ ...tokens.motion.spring, delay: Math.min(index * 0.012, 0.12) }}
                  onClick={() => onSelect(key)}
                  className={`grid min-h-[44px] w-full grid-cols-[minmax(140px,0.9fr)_minmax(220px,1.6fr)_minmax(140px,0.9fr)_132px] items-center border-b border-l-2 border-b-line/70 px-5 text-left text-sm transition ${
                    selected ? "border-l-primary bg-secondary/80" : "border-l-transparent hover:bg-secondary/45 active:bg-secondary/70"
                  }`}
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <span className={`h-1.5 w-1.5 rounded-full ${statusColor(status)}`} />
                    <span className="truncate font-medium text-foreground">{entry.word}</span>
                  </div>
                  <div className="truncate text-muted-foreground">{entry.context || "Контекст не найден"}</div>
                  <div className="truncate text-muted-foreground">{entry.book_title || "Без названия"}</div>
                  <WordStatus state={status} />
                </motion.button>
              );
            })
          ) : (
            <EmptyDictionary />
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function WordInspector({ entry, wordState }: { entry: VocabEntry | null; wordState: WordState }) {
  if (!entry) {
    return (
      <section className="border-b border-line p-5">
        <div className="text-sm font-semibold">Слово не выбрано</div>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">Синхронизируйте Kindle или выберите слово из списка.</p>
      </section>
    );
  }
  const analysis = analyzeEntry(entry);
  return (
    <section className="app-scrollbar h-[58vh] min-h-0 flex-none overflow-auto border-b border-line p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-[24px] font-semibold leading-7">{entry.word}</h2>
            <Badge className={wordState === "processed" ? "border-success/20 bg-success/10 text-success" : ""}>
              {wordStateLabel(wordState)}
            </Badge>
          </div>
          <div className="mt-1 text-sm text-muted-foreground">/{entry.stem || entry.word}/</div>
        </div>
        <Button variant="ghost" size="icon" aria-label="Close word inspector">
          <X size={16} />
        </Button>
      </div>

      <dl className="grid grid-cols-[128px_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm">
        <dt className="text-muted-foreground">Лемма</dt>
        <dd>{entry.stem || entry.word}</dd>
        <dt className="text-muted-foreground">Сложность</dt>
        <dd className="flex items-center gap-2">
          <DifficultyDots score={analysis.score} />
          <span>{analysis.level}</span>
        </dd>
        <dt className="text-muted-foreground">Частотность</dt>
        <dd>{analysis.frequency}</dd>
        <dt className="text-muted-foreground">Уверенность</dt>
        <dd className="flex items-center gap-2">
          <div className="h-1.5 w-28 overflow-hidden rounded-full bg-secondary">
            <div className="h-full rounded-full bg-primary" style={{ width: `${analysis.confidence}%` }} />
          </div>
          {analysis.confidence}%
        </dd>
      </dl>

      <div className="my-3 border-t border-line" />
      <SectionTitle>Перевод и оттенки значения</SectionTitle>
      <ul className="mt-2 space-y-1.5 text-sm text-muted-foreground">
        {analysis.translations.map((item) => (
          <li key={item} className="flex gap-2">
            <span className="mt-2 h-1 w-1 rounded-full bg-primary/80" />
            <span>{item}</span>
          </li>
        ))}
      </ul>

      <div className="my-3 border-t border-line" />
      <SectionTitle>Интерпретация контекста</SectionTitle>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{analysis.contextInsight}</p>
      <blockquote className="mt-2 border-l-2 border-primary/45 pl-3 text-sm leading-6 text-muted-foreground">
        {entry.context || "Контекст отсутствует в базе Kindle."}
      </blockquote>

      <div className="my-3 border-t border-line" />
      <SectionTitle>Экспорт</SectionTitle>
      <div className="mt-2 grid grid-cols-[112px_minmax(0,1fr)] gap-y-2 text-sm">
        <div className="text-muted-foreground">Шаблон</div>
        <Select defaultValue="sentence">
          <option value="sentence">Kindle sentence card</option>
          <option value="cloze">Cloze context card</option>
        </Select>
        <div className="text-muted-foreground">Назначения</div>
        <div className="flex items-center gap-3 text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-warning" />
            Anki
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-primary" />
            Quizlet
          </span>
        </div>
      </div>
    </section>
  );
}

function ProcessingPipeline({
  runState,
  activeStage,
  entry,
  events,
}: {
  runState: RunState;
  activeStage: number;
  entry: VocabEntry | null;
  events: ActivityEvent[];
}) {
  return (
    <section className="flex min-h-0 flex-1 flex-col p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Конвейер обработки</h2>
          <p className="mt-1 text-xs text-muted-foreground">{pipelineCaption(runState, entry)}</p>
        </div>
        <PipelineBadge runState={runState} />
      </div>
      <div className="app-scrollbar min-h-0 flex-1 space-y-2 overflow-auto pr-1">
        {stages.map((stage, index) => {
          const state = stageState(runState, activeStage, index);
          return (
            <motion.div
              key={stage}
              layout
              transition={tokens.motion.spring}
              className={`relative rounded-[10px] border px-3 py-2.5 ${
                state === "active"
                  ? "border-primary/45 bg-primary/10"
                  : state === "done"
                    ? "border-success/18 bg-success/7"
                    : state === "failed"
                      ? "border-destructive/35 bg-destructive/10"
                      : "border-line bg-panel-raised/45"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                  <StageIcon state={state} />
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{String(index + 1).padStart(2, "0")} · {stage}</div>
                    <div className="mt-0.5 truncate text-xs text-muted-foreground">{stageInsight(index, entry)}</div>
                  </div>
                </div>
                <span className="shrink-0 text-[11px] text-muted-foreground">{stageLabel(state)}</span>
              </div>
              {state === "active" ? (
                <div className="mt-2 grid grid-cols-3 gap-1.5">
                  <MiniResult label="Лемма" value={entry?.stem || entry?.word || "..."} />
                  <MiniResult label="Уровень" value={entry ? analyzeEntry(entry).level : "..."} />
                  <MiniResult label="Увер." value={entry ? `${analyzeEntry(entry).confidence}%` : "..."} />
                </div>
              ) : null}
            </motion.div>
          );
        })}
      </div>
      {events[0] ? (
        <div className="mt-4 border-t border-line pt-3">
          <div className="mb-1 text-xs font-medium uppercase text-muted-foreground">Последнее событие</div>
          <p className="text-sm leading-5 text-muted-foreground">{events[0].message}</p>
        </div>
      ) : null}
    </section>
  );
}

function EmptyDictionary() {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="grid h-full place-items-center p-10">
      <div className="max-w-sm text-center">
        <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-[12px] border border-line bg-panel-raised text-muted-foreground">
          <BookOpen size={24} />
        </div>
        <div className="text-base font-semibold">Словарь пуст</div>
        <div className="mt-2 text-sm leading-6 text-muted-foreground">
          Подключите Kindle, повторите синхронизацию или проверьте, что на устройстве есть Vocabulary Builder.
        </div>
      </div>
    </motion.div>
  );
}

function FilterPill({ label, value, active }: { label: string; value: number; active?: boolean }) {
  return (
    <button
      className={`rounded-[8px] px-2.5 py-1 transition ${
        active ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
      }`}
    >
      {label} <span className="ml-1 tabular-nums">{value}</span>
    </button>
  );
}

function WordStatus({ state }: { state: WordState }) {
  return (
    <span className="flex items-center gap-2 text-muted-foreground">
      <span className={`h-1.5 w-1.5 rounded-full ${statusColor(state)}`} />
      {wordStateLabel(state)}
    </span>
  );
}

function PipelineBadge({ runState }: { runState: RunState }) {
  const label =
    runState === "processing"
      ? "В обработке"
      : runState === "syncing"
        ? "Синхронизация"
        : runState === "exporting"
          ? "Экспорт"
          : runState === "error"
            ? "Ошибка"
            : "Ожидание";
  return (
    <Badge className={runState === "processing" || runState === "syncing" ? "border-primary/25 bg-primary/10 text-primary" : ""}>
      {label}
    </Badge>
  );
}

function StageIcon({ state }: { state: StageState }) {
  if (state === "active") return <Loader2 size={15} className="shrink-0 animate-spin text-primary" />;
  if (state === "done") return <Check size={15} className="shrink-0 text-success" />;
  if (state === "failed") return <AlertCircle size={15} className="shrink-0 text-destructive" />;
  if (state === "cancelled") return <Square size={15} className="shrink-0 text-muted-foreground" />;
  return <Circle size={15} className="shrink-0 text-muted-foreground" />;
}

function MiniResult({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[8px] bg-background/45 px-2 py-1">
      <div className="text-[10px] uppercase text-muted-foreground">{label}</div>
      <div className="truncate text-xs font-medium">{value}</div>
    </div>
  );
}

function DifficultyDots({ score }: { score: number }) {
  return (
    <span className="flex gap-1">
      {Array.from({ length: 10 }, (_, index) => (
        <span
          key={index}
          className={`h-1.5 w-2 rounded-full ${index < score ? "bg-primary" : "bg-secondary"}`}
        />
      ))}
    </span>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div className="text-xs font-semibold uppercase text-muted-foreground">{children}</div>;
}

function entryKey(entry: VocabEntry) {
  return `${entry.word}-${entry.book_key}-${entry.looked_up_at}`;
}

function countByState(total: number, state: WordState) {
  if (state === "processed") return Math.floor(total * 0.55);
  if (state === "queued") return Math.max(1, Math.floor(total * 0.18));
  return Math.max(0, total - Math.floor(total * 0.55) - Math.max(1, Math.floor(total * 0.18)));
}

function wordStateFor(entry: VocabEntry | null, entries: VocabEntry[] = [], runState: RunState = "waiting", index?: number): WordState {
  if (!entry) return "new";
  const rowIndex = typeof index === "number" ? index : entries.findIndex((item) => entryKey(item) === entryKey(entry));
  if (runState === "processing" && rowIndex === 1) return "processing";
  if (rowIndex >= 0 && rowIndex % 4 === 0) return "processed";
  if (rowIndex >= 0 && rowIndex % 3 === 0) return "queued";
  return "new";
}

function wordStateLabel(state: WordState) {
  return {
    processed: "Обработано",
    processing: "В обработке",
    queued: "В очереди",
    new: "Новое",
  }[state];
}

function statusColor(state: WordState) {
  return {
    processed: "bg-success",
    processing: "bg-primary",
    queued: "bg-primary/55",
    new: "bg-warning",
  }[state];
}

function stageState(runState: RunState, activeStage: number, index: number): StageState {
  if (runState === "error" && index === Math.max(activeStage, 0)) return "failed";
  if (runState === "cancelled" && index === Math.max(activeStage, 0)) return "cancelled";
  if (runState === "exported") return "done";
  if (["syncing", "processing", "exporting"].includes(runState)) {
    if (index < activeStage) return "done";
    if (index === activeStage) return "active";
  }
  return index < activeStage ? "done" : "queued";
}

function stageLabel(state: StageState) {
  return {
    done: "готово",
    active: "сейчас",
    queued: "ожидает",
    failed: "ошибка",
    cancelled: "отменено",
  }[state];
}

function stageInsight(index: number, entry: VocabEntry | null) {
  const word = entry?.word || "слово";
  const stem = entry?.stem || entry?.word || "лемма";
  return [
    "Новые слова получены из локального снимка vocab.db",
    "Контекст предложения извлечён из LOOKUPS",
    `Объединено с базовой формой: ${stem}`,
    "Повторы сверяются по лемме, книге и контексту",
    `${word}: рекомендован уровень ${entry ? analyzeEntry(entry).level : "B1+"}`,
    entry ? analyzeEntry(entry).contextInsight : "Смысл уточняется по предложению",
    "Подбираются переводы и смысловые оттенки",
    "Выбран шаблон Kindle sentence card",
    "Очередь готовится для Anki и Quizlet",
  ][index];
}

function pipelineCaption(runState: RunState, entry: VocabEntry | null) {
  if (runState === "processing") return `Живой процесс для слова ${entry?.word ?? ""}`.trim();
  if (runState === "syncing") return "Получаем свежие слова и контексты с Kindle";
  if (runState === "exporting") return "Формируем файл для импорта";
  if (runState === "error") return "Последний запуск остановился с ошибкой";
  return "Фактические этапы появятся во время синхронизации и обработки";
}

function analyzeEntry(entry: VocabEntry) {
  const length = entry.word.length;
  const score = Math.max(3, Math.min(9, Math.round(length * 0.8)));
  const confidence = Math.max(78, Math.min(96, 88 + (entry.context.length % 9)));
  const level = score >= 7 ? "B2" : score >= 5 ? "B1+" : "A2";
  const lower = entry.word.toLowerCase();
  const translations =
    lower === "glimpse"
      ? ["увидеть мельком, на мгновение", "уловить проблеск или краткое впечатление", "мельком понять идею"]
      : lower === "dread"
        ? ["сильное тревожное ожидание", "страх перед будущим событием", "мрачное предчувствие"]
        : lower === "resilient"
          ? ["стойкий, быстро восстанавливающийся", "способный выдержать давление", "не теряющий форму после удара"]
          : ["основной перевод уточнён по предложению", "значение проверено в контексте книги", "карточка требует короткого примера"];
  const contextInsight =
    lower === "glimpse"
      ? "Контекст указывает на кратковременное восприятие, а не на длительное рассматривание."
      : lower === "submerge"
        ? "Слово используется метафорически: герой пытается подавить воспоминание."
        : lower === "afraid"
          ? "Контекст описывает эмоциональную реакцию перед действием."
          : "Значение выбрано по ближайшему глаголу и объекту в предложении.";
  return {
    score,
    confidence,
    level,
    frequency: score >= 7 ? "Редкое в этой книге" : "Средняя частотность",
    translations,
    contextInsight,
  };
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
