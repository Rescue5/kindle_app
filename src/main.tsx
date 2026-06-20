import React from "react";
import ReactDOM from "react-dom/client";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  Archive,
  BarChart3,
  BookOpen,
  Check,
  Circle,
  Clock3,
  Database,
  Download,
  FileDown,
  FolderSync,
  Library,
  Loader2,
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
import { tokens } from "@/design/tokens";
import { callBackend, initialState } from "@/lib/backend";
import type { ActivityEvent, AppState, ProcessingStatus, VocabEntry, WordAnalysis } from "@/types";
import "./index.css";

type LoadResult = {
  sourceName: string;
  sourceStatus: string;
  books: AppState["books"];
  entries: VocabEntry[];
};

type EntryUpdate = {
  id: string;
  processing_status: ProcessingStatus;
  analysis?: WordAnalysis;
};

type OptimizeResult = {
  accepted_new: number;
  processed_new: number;
  skipped_existing: number;
  rejected_new?: number;
  tsv_path: string;
  entry_updates?: EntryUpdate[];
  events?: ActivityEvent[];
};

type RunState = "waiting" | "disconnected" | "syncing" | "processing" | "exporting" | "exported" | "error" | "cancelled";
type StageState = "done" | "active" | "queued" | "failed" | "cancelled";
type StatusFilter = "all" | ProcessingStatus;
type ExportFormat = "anki" | "quizlet";

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
  { label: "Библиотека", icon: Library, active: true, enabled: true },
  { label: "Обработка", icon: FolderSync, enabled: false },
  { label: "Экспорты", icon: Archive, enabled: false },
  { label: "Аналитика", icon: BarChart3, enabled: false },
  { label: "Настройки", icon: Settings, enabled: false },
];

function App() {
  const [state, setState] = React.useState<AppState>(() => ({
    ...initialState,
    entries: normalizeEntries(initialState.entries),
  }));
  const [runState, setRunState] = React.useState<RunState>("disconnected");
  const [activeStage, setActiveStage] = React.useState(0);
  const [selectedKey, setSelectedKey] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState<StatusFilter>("all");
  const [exportFormat, setExportFormat] = React.useState<ExportFormat>("anki");
  const [lastError, setLastError] = React.useState("");
  const requestId = React.useRef(0);

  const filteredEntries = React.useMemo(() => {
    const query = state.searchText.trim().toLowerCase();
    const selectedBook = state.books[state.selectedBookIndex];
    return state.entries.filter((entry) => {
      const bookMatch = matchesSelectedBook(entry, selectedBook?.key ?? "", selectedBook?.label ?? "");
      const statusMatch = statusFilter === "all" || entryStatus(entry) === statusFilter;
      const queryMatch =
        !query ||
        [entry.word, entry.stem, entry.context, entry.book_title, entry.authors].some((value) =>
          (value || "").toLowerCase().includes(query),
        );
      return bookMatch && statusMatch && queryMatch;
    });
  }, [state.entries, state.searchText, state.selectedBookIndex, state.books, statusFilter]);

  React.useEffect(() => {
    if (!filteredEntries.length) {
      setSelectedKey("");
      return;
    }
    if (!filteredEntries.some((entry) => entry.id === selectedKey)) {
      setSelectedKey(filteredEntries[0].id);
    }
  }, [filteredEntries, selectedKey]);

  React.useEffect(() => {
    if (!["syncing", "processing", "exporting"].includes(runState)) return;
    const maxStage = runState === "syncing" ? 2 : runState === "exporting" ? 8 : 7;
    const timer = window.setInterval(() => {
      setActiveStage((current) => (current >= maxStage ? current : current + 1));
    }, 850);
    return () => window.clearInterval(timer);
  }, [runState]);

  const selectedEntry = filteredEntries.find((entry) => entry.id === selectedKey) ?? filteredEntries[0] ?? null;
  const busy = ["syncing", "processing", "exporting"].includes(runState);

  async function runLoad(action: "scan" | "load_demo") {
    const id = ++requestId.current;
    setActiveStage(0);
    setRunState(action === "scan" ? "syncing" : "waiting");
    setLastError("");
    setStatusFilter("all");
    setState((current) => ({ ...current, processing: true, statusMessage: "Синхронизируем источник слов..." }));
    try {
      const result = await callBackend<LoadResult>(action, {});
      if (id !== requestId.current) return;
      const entries = normalizeEntries(result.entries);
      setState((current) => ({
        ...current,
        ...result,
        entries,
        selectedBookIndex: 0,
        processing: false,
        dbLoaded: entries.length > 0,
        statusMessage: entries.length ? "Словарь загружен. Слова пока не обработаны." : "Словарь пуст",
        activityEvents: [
          {
            phase: "answered",
            title: "Источник готов",
            message: `${entries.length} слов получено из ${Math.max(result.books.length - 1, 0)} книг.`,
            meta: "Sync",
          },
          ...current.activityEvents,
        ],
      }));
      setRunState(entries.length ? "waiting" : "disconnected");
    } catch (error) {
      fail("Не удалось синхронизировать Kindle", String(error));
    }
  }

  async function runOptimize() {
    const submitted = filteredEntries;
    if (!submitted.length) return;
    const id = ++requestId.current;
    setActiveStage(1);
    setRunState("processing");
    setLastError("");
    setState((current) => ({
      ...current,
      processing: true,
      statusMessage: "Идёт offline-обработка слов...",
      entries: current.entries.map((entry) =>
        submitted.some((item) => item.id === entry.id) ? { ...entry, processing_status: "processing" } : entry,
      ),
    }));
    try {
      const result = await callBackend<OptimizeResult>("optimize", { entries: submitted });
      if (id !== requestId.current) return;
      const updates = result.entry_updates ?? [];
      const updatedIds = new Set(updates.map((update) => update.id));
      const submittedIds = new Set(submitted.map((entry) => entry.id));
      setActiveStage(7);
      setRunState("waiting");
      setState((current) => ({
        ...current,
        processing: false,
        statusMessage: `Offline-обработка завершена: ${result.processed_new} новых групп`,
        entries: current.entries.map((entry) => {
          const update = updates.find((item) => item.id === entry.id);
          if (update) {
            return {
              ...entry,
              processing_status: update.processing_status,
              analysis: update.analysis,
              export_status: update.processing_status === "processed" ? "queued" : entry.export_status,
            };
          }
          if (submittedIds.has(entry.id) && !updatedIds.has(entry.id)) {
            return {
              ...entry,
              processing_status: "skipped",
              analysis: {
                base_form: entry.stem || entry.word,
                accepted: true,
                importance_note: "объединено с другой формой или уже было в snapshot",
                translation_status: "offline_only",
                tsv_path: result.tsv_path,
              },
            };
          }
          return entry;
        }),
        activityEvents: [
          ...(result.events ?? []),
          {
            phase: "answered",
            title: "Offline-обработка завершена",
            message: `Новых групп: ${result.processed_new}; принято: ${result.accepted_new}; отклонено: ${result.rejected_new ?? 0}; уже было: ${result.skipped_existing}.`,
            meta: result.tsv_path,
          },
          ...current.activityEvents,
        ],
      }));
    } catch (error) {
      setState((current) => ({
        ...current,
        entries: current.entries.map((entry) =>
          submitted.some((item) => item.id === entry.id) ? { ...entry, processing_status: "failed" } : entry,
        ),
      }));
      fail("Ошибка offline-обработки", String(error));
    }
  }

  async function runExport() {
    const exportable = filteredEntries.filter((entry) => ["processed", "skipped"].includes(entryStatus(entry)));
    if (!exportable.length) {
      fail("Нет обработанных слов для экспорта", "Сначала запустите offline-обработку выбранной выборки.");
      return;
    }
    const id = ++requestId.current;
    setActiveStage(8);
    setRunState("exporting");
    setLastError("");
    try {
      const result = await callBackend<{ path: string }>("export", { format: exportFormat, entries: exportable });
      if (id !== requestId.current) return;
      const exportedIds = new Set(exportable.map((entry) => entry.id));
      setRunState("exported");
      setState((current) => ({
        ...current,
        processing: false,
        statusMessage: `Экспорт завершён: ${result.path}`,
        entries: current.entries.map((entry) =>
          exportedIds.has(entry.id) ? { ...entry, export_status: "exported" } : entry,
        ),
        activityEvents: [
          {
            phase: "answered",
            title: `${exportFormat.toUpperCase()} экспорт`,
            message: `${exportable.length} обработанных строк сохранено для импорта.`,
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
    setState((current) => ({
      ...current,
      processing: false,
      statusMessage: "Операция отменена",
      entries: current.entries.map((entry) =>
        entry.processing_status === "processing" ? { ...entry, processing_status: "raw" } : entry,
      ),
    }));
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

  const counts = React.useMemo(() => countStatuses(state.entries), [state.entries]);

  return (
    <main className="premium-grid h-full overflow-hidden text-foreground">
      <div className="grid h-full grid-cols-[224px_minmax(620px,1fr)_390px] gap-0">
        <Sidebar state={state} runState={runState} onScan={() => runLoad("scan")} />
        <section className="flex min-w-0 flex-col border-x border-line/80">
          <TopBar
            state={state}
            setState={setState}
            runState={runState}
            busy={busy}
            total={filteredEntries.length}
            counts={counts}
            statusFilter={statusFilter}
            setStatusFilter={setStatusFilter}
            exportFormat={exportFormat}
            setExportFormat={setExportFormat}
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
          <VocabularyList entries={filteredEntries} selectedKey={selectedKey} onSelect={setSelectedKey} />
        </section>
        <aside className="flex min-w-0 flex-col bg-panel/70">
          <WordInspector entry={selectedEntry} onClose={() => setSelectedKey("")} />
          <ProcessingPipeline runState={runState} activeStage={activeStage} entry={selectedEntry} events={state.activityEvents} />
        </aside>
      </div>
    </main>
  );
}

function Sidebar({ state, runState, onScan }: { state: AppState; runState: RunState; onScan: () => void }) {
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
            disabled={!item.enabled}
            title={item.enabled ? item.label : "Раздел будет подключён позже"}
            className={`flex h-10 w-full items-center gap-3 rounded-[10px] px-3 text-left text-sm transition disabled:cursor-not-allowed disabled:opacity-45 ${
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
  busy,
  total,
  counts,
  statusFilter,
  setStatusFilter,
  exportFormat,
  setExportFormat,
  onScan,
  onOptimize,
  onExport,
  onCancel,
}: {
  state: AppState;
  setState: React.Dispatch<React.SetStateAction<AppState>>;
  runState: RunState;
  busy: boolean;
  total: number;
  counts: Record<ProcessingStatus, number>;
  statusFilter: StatusFilter;
  setStatusFilter: (value: StatusFilter) => void;
  exportFormat: ExportFormat;
  setExportFormat: (value: ExportFormat) => void;
  onScan: () => void;
  onOptimize: () => void;
  onExport: () => void;
  onCancel: () => void;
}) {
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
      <div className="grid grid-cols-[minmax(260px,1fr)_220px_142px_110px] gap-3">
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
          value={exportFormat}
          disabled={busy || !total}
          onChange={(event) => setExportFormat(event.target.value as ExportFormat)}
        >
          <option value="anki">Anki</option>
          <option value="quizlet">Quizlet</option>
        </Select>
        <Button variant="secondary" onClick={onExport} disabled={busy || !total}>
          <Download size={15} />
          Экспорт
        </Button>
      </div>
      <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          <FilterPill label="Все" value={state.entries.length} active={statusFilter === "all"} onClick={() => setStatusFilter("all")} />
          <FilterPill label="Новые" value={counts.raw} active={statusFilter === "raw"} onClick={() => setStatusFilter("raw")} />
          <FilterPill label="Обработанные" value={counts.processed} active={statusFilter === "processed"} onClick={() => setStatusFilter("processed")} />
          <FilterPill label="Отклонённые" value={counts.rejected} active={statusFilter === "rejected"} onClick={() => setStatusFilter("rejected")} />
          <FilterPill label="Пропущенные" value={counts.skipped} active={statusFilter === "skipped"} onClick={() => setStatusFilter("skipped")} />
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
      title: "Offline-обработка",
      text: "Нормализуем формы, удаляем дубли и считаем механическую полезность без нейросети.",
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
  onSelect,
}: {
  entries: VocabEntry[];
  selectedKey: string;
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
              const selected = entry.id === selectedKey;
              const status = entryStatus(entry);
              return (
                <motion.button
                  key={entry.id}
                  type="button"
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ ...tokens.motion.spring, delay: Math.min(index * 0.008, 0.08) }}
                  onClick={() => onSelect(entry.id)}
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

function WordInspector({ entry, onClose }: { entry: VocabEntry | null; onClose: () => void }) {
  if (!entry) {
    return (
      <section className="border-b border-line p-5">
        <div className="text-sm font-semibold">Слово не выбрано</div>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">Синхронизируйте Kindle или выберите слово из списка.</p>
      </section>
    );
  }
  const status = entryStatus(entry);
  const analysis = entry.analysis;
  const processed = Boolean(analysis) && status !== "raw" && status !== "processing";
  return (
    <section className="app-scrollbar h-[58vh] min-h-0 flex-none overflow-auto border-b border-line p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-[24px] font-semibold leading-7">{entry.word}</h2>
            <Badge className={status === "processed" ? "border-success/20 bg-success/10 text-success" : ""}>
              {statusLabel(status)}
            </Badge>
          </div>
          <div className="mt-1 text-sm text-muted-foreground">/{entry.stem || entry.word}/</div>
        </div>
        <Button variant="ghost" size="icon" aria-label="Снять выбор слова" onClick={onClose}>
          <X size={16} />
        </Button>
      </div>

      {!processed || !analysis ? (
        <UnprocessedInspector entry={entry} status={status} />
      ) : (
        <ProcessedInspector entry={entry} analysis={analysis} />
      )}
    </section>
  );
}

function UnprocessedInspector({ entry, status }: { entry: VocabEntry; status: ProcessingStatus }) {
  return (
    <div className="space-y-4">
      <div className="rounded-[10px] border border-line bg-panel-raised/55 p-3">
        <div className="text-sm font-medium">{status === "processing" ? "Слово сейчас обрабатывается" : "Слово ещё не обработано"}</div>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          Лемма, сложность, смысловые оттенки, перевод и карточка появятся только после offline-обработки или будущего LLM-обогащения.
        </p>
      </div>
      <SectionTitle>Оригинальный контекст</SectionTitle>
      <blockquote className="border-l-2 border-line pl-3 text-sm leading-6 text-muted-foreground">
        {entry.context || "Контекст отсутствует в базе Kindle."}
      </blockquote>
      <SectionTitle>Источник</SectionTitle>
      <dl className="grid grid-cols-[96px_minmax(0,1fr)] gap-2 text-sm">
        <dt className="text-muted-foreground">Книга</dt>
        <dd className="truncate">{entry.book_title || "Без названия"}</dd>
        <dt className="text-muted-foreground">Дата</dt>
        <dd>{entry.looked_up_at || "неизвестно"}</dd>
      </dl>
    </div>
  );
}

function ProcessedInspector({ entry, analysis }: { entry: VocabEntry; analysis: WordAnalysis }) {
  const score = typeof analysis.importance_score === "number" ? analysis.importance_score : undefined;
  const hasLlmTranslation = analysis.translation_status === "llm_enriched" && Boolean(analysis.russian_meanings);
  return (
    <div>
      <dl className="grid grid-cols-[128px_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm">
        <dt className="text-muted-foreground">Лемма</dt>
        <dd>{analysis.base_form || entry.stem || entry.word}</dd>
        <dt className="text-muted-foreground">Часть речи</dt>
        <dd>{analysis.pos || "не определена"}</dd>
        <dt className="text-muted-foreground">Сложность</dt>
        <dd className="flex items-center gap-2">
          {typeof score === "number" ? <DifficultyDots score={score} /> : null}
          <span>{typeof score === "number" ? `${score}/10` : "не рассчитана"}</span>
        </dd>
        <dt className="text-muted-foreground">Частотность</dt>
        <dd>{analysis.frequency_note || "нет данных"}</dd>
      </dl>

      <Divider />
      <SectionTitle>Перевод и оттенки значения</SectionTitle>
      {hasLlmTranslation ? (
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{analysis.russian_meanings}</p>
      ) : (
        <EmptyField text="Не заполнено. Это поле появится после LLM-обогащения." />
      )}

      <Divider />
      <SectionTitle>Offline-заметка</SectionTitle>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{analysis.importance_note || "Локальная обработка завершена без дополнительной заметки."}</p>

      <Divider />
      <SectionTitle>Интерпретация контекста</SectionTitle>
      {analysis.generated_context_ru || analysis.generated_context_en ? (
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{analysis.generated_context_ru || analysis.generated_context_en}</p>
      ) : (
        <EmptyField text="Не заполнено. Offline-обработка не генерирует смысловую интерпретацию предложения." />
      )}
      <blockquote className="mt-2 border-l-2 border-primary/45 pl-3 text-sm leading-6 text-muted-foreground">
        {entry.context || "Контекст отсутствует в базе Kindle."}
      </blockquote>

      <Divider />
      <SectionTitle>Экспорт</SectionTitle>
      <dl className="mt-2 grid grid-cols-[112px_minmax(0,1fr)] gap-y-2 text-sm">
        <dt className="text-muted-foreground">Шаблон</dt>
        <dd>Kindle sentence card</dd>
        <dt className="text-muted-foreground">Состояние</dt>
        <dd>{exportLabel(entry.export_status)}</dd>
      </dl>
    </div>
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
          const state = stageState(runState, activeStage, index, entry);
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
                    <div className="truncate text-sm font-medium">
                      {String(index + 1).padStart(2, "0")} · {stage}
                    </div>
                    <div className="mt-0.5 truncate text-xs text-muted-foreground">{stageInsight(index, entry, state)}</div>
                  </div>
                </div>
                <span className="shrink-0 text-[11px] text-muted-foreground">{stageLabel(state)}</span>
              </div>
              {state === "active" && entry?.analysis ? (
                <div className="mt-2 grid grid-cols-3 gap-1.5">
                  <MiniResult label="Лемма" value={entry.analysis.base_form || entry.stem || entry.word} />
                  <MiniResult label="Score" value={entry.analysis.importance_score != null ? `${entry.analysis.importance_score}/10` : "..."} />
                  <MiniResult label="Статус" value={statusLabel(entryStatus(entry))} />
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
        <div className="text-base font-semibold">Нет слов в выборке</div>
        <div className="mt-2 text-sm leading-6 text-muted-foreground">
          Измените фильтр, повторите синхронизацию или проверьте Vocabulary Builder на Kindle.
        </div>
      </div>
    </motion.div>
  );
}

function FilterPill({
  label,
  value,
  active,
  onClick,
}: {
  label: string;
  value: number;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-[8px] px-2.5 py-1 transition ${
        active ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
      }`}
    >
      {label} <span className="ml-1 tabular-nums">{value}</span>
    </button>
  );
}

function WordStatus({ state }: { state: ProcessingStatus }) {
  return (
    <span className="flex items-center gap-2 text-muted-foreground">
      <span className={`h-1.5 w-1.5 rounded-full ${statusColor(state)}`} />
      {statusLabel(state)}
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
        <span key={index} className={`h-1.5 w-2 rounded-full ${index < score ? "bg-primary" : "bg-secondary"}`} />
      ))}
    </span>
  );
}

function Divider() {
  return <div className="my-3 border-t border-line" />;
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div className="text-xs font-semibold uppercase text-muted-foreground">{children}</div>;
}

function EmptyField({ text }: { text: string }) {
  return <div className="mt-2 rounded-[10px] border border-dashed border-line bg-background/30 p-3 text-sm text-muted-foreground">{text}</div>;
}

function normalizeEntries(entries: VocabEntry[]): VocabEntry[] {
  return entries.map((entry) => ({
    ...entry,
    id: entry.id || stableEntryId(entry),
    processing_status: entry.processing_status || "raw",
    export_status: entry.export_status || "none",
  }));
}

function stableEntryId(entry: VocabEntry) {
  return [entry.word, entry.stem, entry.context, entry.book_key, entry.book_title, entry.looked_up_at].join("|");
}

function matchesSelectedBook(entry: VocabEntry, selectedKey: string, selectedLabel: string) {
  if (!selectedKey) return true;
  if (entry.book_key === selectedKey) return true;
  if (entry.book_title && selectedLabel.toLowerCase().includes(entry.book_title.toLowerCase())) return true;
  return false;
}

function entryStatus(entry: VocabEntry): ProcessingStatus {
  return entry.processing_status || "raw";
}

function countStatuses(entries: VocabEntry[]): Record<ProcessingStatus, number> {
  return entries.reduce(
    (acc, entry) => {
      acc[entryStatus(entry)] += 1;
      return acc;
    },
    { raw: 0, processing: 0, processed: 0, rejected: 0, skipped: 0, failed: 0 } as Record<ProcessingStatus, number>,
  );
}

function statusLabel(state: ProcessingStatus) {
  return {
    raw: "Новое",
    processing: "В обработке",
    processed: "Обработано",
    rejected: "Отклонено",
    skipped: "Пропущено",
    failed: "Ошибка",
  }[state];
}

function statusColor(state: ProcessingStatus) {
  return {
    raw: "bg-warning",
    processing: "bg-primary",
    processed: "bg-success",
    rejected: "bg-destructive",
    skipped: "bg-muted-foreground",
    failed: "bg-destructive",
  }[state];
}

function exportLabel(value: VocabEntry["export_status"]) {
  return {
    none: "не готово",
    queued: "готово к экспорту",
    exported: "экспортировано",
    failed: "ошибка экспорта",
  }[value || "none"];
}

function stageState(runState: RunState, activeStage: number, index: number, entry: VocabEntry | null): StageState {
  if (runState === "error" && index === Math.max(activeStage, 0)) return "failed";
  if (runState === "cancelled" && index === Math.max(activeStage, 0)) return "cancelled";
  if (runState === "exported") return "done";
  if (["syncing", "processing", "exporting"].includes(runState)) {
    if (index < activeStage) return "done";
    if (index === activeStage) return "active";
  }
  if (entry && entryStatus(entry) !== "raw" && entryStatus(entry) !== "processing") {
    return index <= 4 ? "done" : "queued";
  }
  return "queued";
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

function stageInsight(index: number, entry: VocabEntry | null, state: StageState) {
  if (!entry) return "Выберите слово, чтобы увидеть его состояние.";
  if (state === "queued") {
    return entryStatus(entry) === "raw" ? "Ожидает запуска обработки." : "Будет заполнено после следующего этапа.";
  }
  const analysis = entry.analysis;
  return [
    "Слова получены из локального снимка vocab.db.",
    "Контекст взят из Kindle LOOKUPS.",
    analysis?.base_form ? `Базовая форма: ${analysis.base_form}.` : `Исходная форма: ${entry.stem || entry.word}.`,
    analysis?.source_occurrence_count ? `Объединено в группу: ${analysis.source_occurrence_count}.` : "Дубликаты сверяются по лемме и контексту.",
    analysis?.importance_score != null ? `Оценка полезности: ${analysis.importance_score}/10.` : "Оценка ещё не рассчитана.",
    "Смысловая интерпретация появится после LLM-обогащения.",
    "Переводы появятся после LLM-обогащения.",
    analysis ? "Offline-строка готова для карточки." : "Карточка ещё не сформирована.",
    exportLabel(entry.export_status),
  ][index];
}

function pipelineCaption(runState: RunState, entry: VocabEntry | null) {
  if (runState === "processing") return `Offline-конвейер для выборки; активное слово: ${entry?.word ?? "не выбрано"}`;
  if (runState === "syncing") return "Получаем свежие слова и контексты с Kindle";
  if (runState === "exporting") return "Формируем файл для импорта";
  if (runState === "error") return "Последний запуск остановился с ошибкой";
  return "Показывает только фактические результаты обработки";
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
