import * as React from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  BookMarked,
  BookOpen,
  Check,
  ChevronDown,
  Circle,
  CloudOff,
  Database,
  Download,
  HardDrive,
  Layers3,
  Loader2,
  RefreshCw,
  Search,
  Square,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { counts, isAcceptedNew, obsidianSyncReason, primaryOccurrence, processingLabel, processingTone, type QuickFilter } from "./domain";
import type { useLibraryController } from "./use-library-controller";
import type { ConnectorInfo, LexemeRecord, Operation, WordAnalysis } from "@/types";

type Controller = ReturnType<typeof useLibraryController>;

export const LibraryWorkspace = React.memo(function LibraryWorkspace({ controller }: { controller: Controller }) {
  const [exportFormat, setExportFormat] = React.useState<"anki" | "quizlet">(controller.settings.default_export_format);
  React.useEffect(() => setExportFormat(controller.settings.default_export_format), [controller.settings.default_export_format]);
  const totals = React.useMemo(() => counts(controller.entries), [controller.entries]);
  const busy = controller.operation.status === "running";
  const obsidianEnabled = controller.settings.obsidian_sync_enabled;

  return (
    <div className="grid min-h-0 flex-1 grid-cols-[minmax(560px,1fr)_340px] overflow-hidden bg-background/35">
      <main className="flex min-h-0 min-w-0 flex-col border-r border-line">
        <header className="flex-none border-b border-line px-5 pb-3 pt-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-[21px] font-semibold leading-7">Библиотека</h1>
              <p className="mt-0.5 text-xs text-muted-foreground">Леммы, формы и контексты Kindle Vocabulary Builder</p>
            </div>
            <div className="flex items-center gap-2">
              {busy ? (
                <Button variant="secondary" size="sm" onClick={() => void controller.cancel()}>
                  <Square size={14} /> Отменить
                </Button>
              ) : null}
              <ConnectorButton kind="kindle" info={controller.connectors.kindle} onClick={() => void controller.syncKindle()} disabled={busy || controller.connectors.kindle.state !== "connected"} />
              {obsidianEnabled ? (
                <ConnectorButton kind="obsidian" info={controller.connectors.obsidian} onClick={() => void controller.syncObsidian()} disabled={busy || controller.connectors.obsidian.state !== "connected"} />
              ) : null}
              {controller.queueStatus.total > 0 ? (
                <div className="flex h-8 items-center gap-1.5 rounded-[7px] border border-line bg-panel-raised/45 px-2.5 text-xs text-muted-foreground" title="Автоматическая очередь offline-обработки">
                  {controller.operation.kind === "processing" && busy ? <Loader2 size={13} className="animate-spin text-primary" /> : <Layers3 size={13} />}
                  <span className="tabular-nums">{controller.queueStatus.total}</span>
                </div>
              ) : null}
            </div>
          </div>

          <div className="mt-4 grid grid-cols-[minmax(240px,1fr)_200px_90px_auto] gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input className="pl-9" value={controller.query} onChange={(event) => controller.setQuery(event.target.value)} placeholder="Поиск слова, контекста или книги..." />
            </div>
            <Select value={controller.selectedBookKey} onChange={(event) => controller.setSelectedBookKey(event.target.value)}>
              {controller.books.map((book) => <option key={book.key || "all"} value={book.key}>{book.label}</option>)}
            </Select>
            <Select value={exportFormat} onChange={(event) => setExportFormat(event.target.value as "anki" | "quizlet")} disabled={busy}>
              <option value="anki">Anki</option>
              <option value="quizlet">Quizlet</option>
            </Select>
            <Button variant="secondary" size="sm" onClick={() => void controller.exportVisible(exportFormat)} disabled={busy || totals.ready === 0}>
              <Download size={14} /> Экспорт
            </Button>
          </div>

          <div className="mt-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-1">
              <QuickFilterButton label="Все" value={totals.all} filter="all" current={controller.quickFilter} onChange={controller.setQuickFilter} />
              <QuickFilterButton label="Новые" value={totals.new} filter="new" current={controller.quickFilter} onChange={controller.setQuickFilter} />
              <QuickFilterButton label="На обработку" value={totals.pending} filter="pending" current={controller.quickFilter} onChange={controller.setQuickFilter} />
              <QuickFilterButton label="Готовые" value={totals.ready} filter="ready" current={controller.quickFilter} onChange={controller.setQuickFilter} />
              {obsidianEnabled ? <QuickFilterButton label="Не в Obsidian" value={totals.unsynced} filter="unsynced" current={controller.quickFilter} onChange={controller.setQuickFilter} obsidian /> : null}
            </div>
            <span className="text-xs tabular-nums text-muted-foreground">{controller.visibleEntries.length} из {controller.entries.length}</span>
          </div>
        </header>

        <ConnectorNotice connector={controller.connectors.kindle} />
        <LexemeTable entries={controller.visibleEntries} selectedId={controller.selectedEntry?.id ?? ""} onSelect={controller.setSelectedId} obsidianEnabled={obsidianEnabled} loading={controller.loading} />
      </main>

      <aside className="flex min-h-0 flex-col bg-panel/65">
        <LexemeInspector entry={controller.selectedEntry} obsidianEnabled={obsidianEnabled} />
        <OperationRail operation={controller.operation} onRetry={controller.retry} onDismiss={controller.dismissOperation} />
      </aside>
    </div>
  );
});

function ConnectorButton({ kind, info, onClick, disabled }: { kind: "kindle" | "obsidian"; info: ConnectorInfo; onClick: () => void; disabled: boolean }) {
  const connected = info.state === "connected";
  const isObsidian = kind === "obsidian";
  const Icon = isObsidian ? Database : HardDrive;
  const activeClass = isObsidian
    ? "border-purple-500/40 bg-purple-500/10 text-purple-200 shadow-[0_0_16px_rgba(168,85,247,0.12)]"
    : "border-sky-500/35 bg-sky-500/10 text-sky-200 shadow-[0_0_16px_rgba(56,189,248,0.10)]";
  return (
    <Button variant="secondary" size="sm" onClick={onClick} disabled={disabled} className={connected ? activeClass : ""} title={`${info.label}: ${connectorLabel(info.state)}`}>
      <Icon size={14} />
      {isObsidian ? "Obsidian" : "Kindle"}
      <span className={`h-1.5 w-1.5 rounded-full ${connected ? (isObsidian ? "bg-purple-300" : "bg-sky-300") : info.state === "error" ? "bg-destructive" : "bg-muted-foreground/60"}`} />
    </Button>
  );
}

function ConnectorNotice({ connector }: { connector: ConnectorInfo }) {
  if (connector.state !== "disconnected") return null;
  return (
    <div className="flex items-center gap-2 border-b border-line bg-panel-raised/35 px-5 py-2 text-xs text-muted-foreground">
      <CloudOff size={14} className="text-warning" />
      Kindle не подключён. Локальная библиотека доступна, синхронизация возобновится после подключения USB.
    </div>
  );
}

function QuickFilterButton({ label, value, filter, current, onChange, obsidian = false }: { label: string; value: number; filter: QuickFilter; current: QuickFilter; onChange: (filter: QuickFilter) => void; obsidian?: boolean }) {
  const active = current === filter;
  return (
    <button type="button" onClick={() => onChange(filter)} className={`rounded-[7px] px-2.5 py-1.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/45 ${active ? (obsidian ? "bg-purple-500/12 text-purple-200" : "bg-secondary text-foreground") : "text-muted-foreground hover:bg-secondary/55 hover:text-foreground"}`}>
      {label} <span className="ml-1 tabular-nums opacity-70">{value}</span>
    </button>
  );
}

const ITEM_HEIGHT = 48;
const OVERSCAN = 5;

const LexemeTable = React.memo(function LexemeTable({ entries, selectedId, onSelect, obsidianEnabled, loading }: { entries: LexemeRecord[]; selectedId: string; onSelect: (id: string) => void; obsidianEnabled: boolean; loading: boolean }) {
  const [container, setContainer] = React.useState<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = React.useState(0);
  const [viewportHeight, setViewportHeight] = React.useState(0);

  const setContainerRef = React.useCallback((el: HTMLDivElement | null) => {
    setContainer(el);
    if (el) {
      setViewportHeight(el.clientHeight);
      setScrollTop(el.scrollTop);
    }
  }, []);

  React.useEffect(() => {
    if (!container) return;
    const handleScroll = () => setScrollTop(container.scrollTop);
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setViewportHeight(entry.contentRect.height);
      }
    });
    container.addEventListener("scroll", handleScroll, { passive: true });
    observer.observe(container);
    return () => {
      container.removeEventListener("scroll", handleScroll);
      observer.disconnect();
    };
  }, [container]);

  React.useEffect(() => {
    if (!container || !selectedId) return;
    const index = entries.findIndex((entry) => entry.id === selectedId);
    if (index === -1) return;
    const rowTop = index * ITEM_HEIGHT;
    const rowBottom = rowTop + ITEM_HEIGHT;
    const viewTop = container.scrollTop;
    const viewBottom = viewTop + container.clientHeight;
    if (rowTop < viewTop || rowBottom > viewBottom) {
      container.scrollTo({ top: rowTop, behavior: "auto" });
    }
  }, [selectedId, entries, container]);

  if (loading) return <div className="grid min-h-0 flex-1 place-items-center text-sm text-muted-foreground"><Loader2 size={20} className="mb-2 animate-spin" />Загружаем локальный каталог</div>;
  if (!entries.length) return <EmptyLibrary />;

  const totalHeight = entries.length * ITEM_HEIGHT;
  const startIndex = Math.max(0, Math.floor(scrollTop / ITEM_HEIGHT) - OVERSCAN);
  const endIndex = Math.min(entries.length - 1, Math.ceil((scrollTop + viewportHeight) / ITEM_HEIGHT) + OVERSCAN);
  const topHeight = startIndex * ITEM_HEIGHT;
  const bottomHeight = Math.max(0, (entries.length - endIndex - 1) * ITEM_HEIGHT);
  const visibleEntries = entries.slice(startIndex, endIndex + 1);

  return (
    <div className="min-h-0 flex-1 overflow-hidden">
      <div className={`grid h-10 items-center border-b border-line bg-panel-raised/25 px-5 text-[11px] font-medium uppercase text-muted-foreground ${obsidianEnabled ? "grid-cols-[minmax(105px,.75fr)_minmax(170px,1.45fr)_minmax(105px,.85fr)_112px_104px]" : "grid-cols-[minmax(110px,.8fr)_minmax(190px,1.5fr)_minmax(115px,.9fr)_118px]"}`}>
        <span>Лемма</span><span>Последний контекст</span><span>Книга</span><span>Обработка</span>{obsidianEnabled ? <span>Obsidian</span> : null}
      </div>
      <div ref={setContainerRef} className="app-scrollbar h-[calc(100%-2.5rem)] overflow-y-auto">
        {topHeight > 0 ? <div style={{ height: topHeight, gridColumn: "1 / -1" }} /> : null}
        {visibleEntries.map((entry) => (
          <LexemeRow key={entry.id} entry={entry} selected={entry.id === selectedId} onSelect={onSelect} obsidianEnabled={obsidianEnabled} />
        ))}
        {bottomHeight > 0 ? <div style={{ height: bottomHeight, gridColumn: "1 / -1" }} /> : null}
      </div>
    </div>
  );
});

const LexemeRow = React.memo(function LexemeRow({ entry, selected, onSelect, obsidianEnabled }: { entry: LexemeRecord; selected: boolean; onSelect: (id: string) => void; obsidianEnabled: boolean }) {
  const occurrence = primaryOccurrence(entry);
  return (
    <button type="button" onClick={() => onSelect(entry.id)} className={`grid min-h-[48px] w-full items-center border-b border-l-2 border-b-line/70 px-5 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/45 ${obsidianEnabled ? "grid-cols-[minmax(105px,.75fr)_minmax(170px,1.45fr)_minmax(105px,.85fr)_112px_104px]" : "grid-cols-[minmax(110px,.8fr)_minmax(190px,1.5fr)_minmax(115px,.9fr)_118px]"} ${selected ? "border-l-primary bg-secondary/75" : "border-l-transparent hover:bg-secondary/40 active:bg-secondary/65"}`}>
      <div className="min-w-0 pr-3">
        <div className="flex items-center gap-2">
          <span className="truncate font-medium text-foreground">{entry.lemma}</span>
          {isAcceptedNew(entry) ? <span className="rounded-[5px] bg-primary/12 px-1.5 py-0.5 text-[10px] font-medium text-primary">Новое</span> : null}
        </div>
        <div className="mt-0.5 flex items-center gap-1.5 overflow-hidden whitespace-nowrap text-[10px] text-muted-foreground">
          {entry.sources.kindle ? <BookOpen size={11} aria-label="Kindle" /> : null}
          {entry.destinations.obsidian.state === "synced" ? <Database size={11} className="text-purple-300" aria-label="Obsidian" /> : null}
          {entry.forms.length > 1 ? <span>{entry.forms.length} формы</span> : null}
          {entry.occurrences.length > 1 ? <span>· {entry.occurrences.length} контекста</span> : null}
        </div>
      </div>
      <span className="truncate pr-4 text-muted-foreground">{occurrence?.context || "Контекст отсутствует"}</span>
      <span className="truncate pr-4 text-muted-foreground">{occurrence?.book_title || "Без книги"}</span>
      <ProcessingMark entry={entry} />
      {obsidianEnabled ? <ObsidianMark entry={entry} /> : null}
    </button>
  );
});

function ProcessingMark({ entry }: { entry: LexemeRecord }) {
  const state = entry.processing.state;
  return <span className={`flex items-center gap-2 text-xs ${processingTone(state)}`}><span className={`h-1.5 w-1.5 rounded-full bg-current ${state === "processing" ? "animate-pulse" : ""}`} />{processingLabel(state)}</span>;
}

function ObsidianMark({ entry }: { entry: LexemeRecord }) {
  const synced = entry.destinations.obsidian.state === "synced";
  const missing = entry.destinations.obsidian.eligible && entry.destinations.obsidian.state === "missing";
  const label = synced ? "В Obsidian" : missing ? "Не в Obsidian" : "Не отправляется";
  return <span className={`flex items-center gap-1.5 text-xs ${synced ? "text-purple-300" : "text-muted-foreground"}`} title={obsidianSyncReason(entry)}>{synced ? <Check size={12} /> : <Circle size={11} />}{label}</span>;
}

function LexemeInspector({ entry, obsidianEnabled }: { entry: LexemeRecord | null; obsidianEnabled: boolean }) {
  if (!entry) return <div className="grid min-h-0 flex-1 place-items-center p-8 text-center text-sm text-muted-foreground">Выберите лемму в библиотеке</div>;
  const analysis = entry.processing.analysis;
  return (
    <section className="app-scrollbar min-h-0 flex-1 overflow-y-auto px-5 pb-6 pt-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="truncate text-[23px] font-semibold leading-7">{entry.lemma}</h2>
            {isAcceptedNew(entry) ? <Badge>Новое</Badge> : null}
          </div>
          <p className="mt-1 truncate text-xs text-muted-foreground">{entry.forms.join(" · ")}</p>
        </div>
        <div className="flex items-center gap-1.5 text-muted-foreground">
          {entry.sources.kindle ? <span title="Есть в Kindle"><BookOpen size={15} /></span> : null}
          {entry.destinations.obsidian.state === "synced" ? <Database size={15} className="text-purple-300" aria-label="Есть в Obsidian" /> : null}
        </div>
      </div>

      <InspectorSection title="Обработка">
        <div className="flex items-center justify-between gap-3 text-sm"><span className="text-muted-foreground">Состояние</span><ProcessingMark entry={entry} /></div>
        {entry.processing.error ? <p className="mt-2 text-xs leading-5 text-destructive">{entry.processing.error}</p> : null}
        {analysis ? <AnalysisDetails analysis={analysis} /> : <p className="mt-3 text-sm leading-6 text-muted-foreground">Лемма ещё не проходила offline-обработку. Оценки, перевод и смысловые поля не заполняются заранее.</p>}
      </InspectorSection>

      {obsidianEnabled ? (
        <InspectorSection title="Obsidian" purple>
          <ObsidianMark entry={entry} />
          <p className="mt-2 text-xs leading-5 text-muted-foreground">{obsidianSyncReason(entry)}</p>
        </InspectorSection>
      ) : null}

      <InspectorSection title={`Контексты · ${entry.occurrences.length}`}>
        <div className="space-y-4">
          {entry.occurrences.map((occurrence) => (
            <article key={occurrence.id} className="border-l-2 border-line pl-3">
              <p className="text-sm leading-6 text-foreground/90">{occurrence.context || "Контекст отсутствует"}</p>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
                <BookOpen size={11} />
                <span>{occurrence.book_title || "Источник без названия"}</span>
                {occurrence.authors ? <span>· {occurrence.authors}</span> : null}
                {occurrence.looked_up_at ? <span>· {occurrence.looked_up_at}</span> : null}
              </div>
            </article>
          ))}
        </div>
      </InspectorSection>
    </section>
  );
}

function AnalysisDetails({ analysis }: { analysis: WordAnalysis }) {
  const translated = analysis.translation_status === "llm_enriched" && Boolean(analysis.russian_meanings);
  return (
    <div className="mt-3 space-y-3 border-t border-line pt-3 text-sm">
      <dl className="grid grid-cols-[110px_minmax(0,1fr)] gap-x-3 gap-y-2">
        <dt className="text-muted-foreground">Часть речи</dt><dd>{analysis.pos || "не определена"}</dd>
        <dt className="text-muted-foreground">Полезность</dt><dd>{analysis.importance_score != null ? `${analysis.importance_score}/10` : "не рассчитана"}</dd>
        <dt className="text-muted-foreground">Частотность</dt><dd>{analysis.frequency_note || "нет данных"}</dd>
      </dl>
      {analysis.importance_note ? <p className="leading-6 text-muted-foreground">{analysis.importance_note}</p> : null}
      <div className="border-t border-line pt-3">
        <div className="text-xs font-medium uppercase text-muted-foreground">Перевод и оттенки</div>
        <p className="mt-2 leading-6 text-muted-foreground">{translated ? analysis.russian_meanings : "Не заполнено. Появится только после LLM-обогащения."}</p>
      </div>
    </div>
  );
}

function InspectorSection({ title, children, purple = false }: { title: string; children: React.ReactNode; purple?: boolean }) {
  return <div className={`mt-5 border-t pt-4 ${purple ? "border-purple-500/25" : "border-line"}`}><h3 className={`mb-3 text-[11px] font-semibold uppercase ${purple ? "text-purple-300" : "text-muted-foreground"}`}>{title}</h3>{children}</div>;
}

function OperationRail({ operation, onRetry, onDismiss }: { operation: Operation; onRetry: () => void; onDismiss: () => void }) {
  const expanded = operation.status !== "idle";
  const progress = operation.total > 0 ? `${operation.current}/${operation.total}` : "";
  return (
    <motion.section className="flex-none border-t border-line bg-background/45 px-5 py-3">
      <div className="flex items-center gap-3">
        <OperationIcon operation={operation} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3"><span className="truncate text-xs font-medium">{operation.title}</span><span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">{progress}</span></div>
          <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{operation.message}</p>
        </div>
      </div>
      <AnimatePresence initial={false}>
        {expanded && operation.stage !== "idle" ? (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="mt-3 flex items-center gap-2 border-t border-line pt-2 text-[11px] text-muted-foreground"><span className="uppercase">{operation.stage}</span><span>·</span><span>фактическое состояние операции</span></div>
          </motion.div>
        ) : null}
      </AnimatePresence>
      {operation.status === "error" || operation.status === "cancelled" ? (
        <div className="mt-3 flex items-center gap-2 border-t border-line pt-2">
          <Button variant="secondary" size="sm" onClick={onRetry}><RefreshCw size={13} />Повторить</Button>
          <Button variant="ghost" size="sm" onClick={onDismiss}>Скрыть</Button>
        </div>
      ) : null}
    </motion.section>
  );
}

function OperationIcon({ operation }: { operation: Operation }) {
  if (operation.status === "running") return <Loader2 size={15} className="shrink-0 animate-spin text-primary" />;
  if (operation.status === "completed") return <Check size={15} className="shrink-0 text-success" />;
  if (operation.status === "error") return <AlertCircle size={15} className="shrink-0 text-destructive" />;
  if (operation.status === "cancelled") return <X size={15} className="shrink-0 text-muted-foreground" />;
  return <Circle size={15} className="shrink-0 text-muted-foreground" />;
}

function EmptyLibrary() {
  return <div className="grid min-h-0 flex-1 place-items-center p-8 text-center"><div><BookMarked size={28} className="mx-auto text-muted-foreground" /><h2 className="mt-3 text-sm font-medium">В этой выборке нет лемм</h2><p className="mt-1 text-xs text-muted-foreground">Измените фильтр, книгу или поисковый запрос.</p></div></div>;
}

function connectorLabel(state: ConnectorInfo["state"]) {
  return { unknown: "не проверено", checking: "проверяется", connected: "подключён", disconnected: "не подключён", disabled: "выключен", error: "ошибка" }[state];
}
