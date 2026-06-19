import React from "react";
import ReactDOM from "react-dom/client";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  BarChart3,
  BookOpen,
  Brain,
  Database,
  Download,
  FileDown,
  FolderOpen,
  Languages,
  RefreshCw,
  Search,
  Sparkles,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Select } from "@/components/ui/select";
import { callBackend, initialState } from "@/lib/backend";
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
  tsv_path: string;
  events?: ActivityEvent[];
};

function App() {
  const [state, setState] = React.useState<AppState>(initialState);
  const [busyLabel, setBusyLabel] = React.useState<string>("");

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

  async function runLoad(action: "scan" | "load_demo") {
    setBusyLabel(action === "scan" ? "Scanning Kindle" : "Loading demo");
    setState((current) => ({
      ...current,
      processing: true,
      activityEvents: [
        {
          phase: "thinking",
          title: action === "scan" ? "Device scan" : "Demo workspace",
          message: "Resolving source and preparing vocabulary data.",
          meta: "Working",
        },
        ...current.activityEvents,
      ],
    }));
    try {
      const result = await callBackend<LoadResult>(action, {});
      setState((current) => ({
        ...current,
        ...result,
        selectedBookIndex: 0,
        processing: false,
        statusMessage: "Vocabulary loaded",
        activityEvents: [
          {
            phase: "answered",
            title: "Source ready",
            message: `${result.entries.length} lookups available across ${Math.max(result.books.length - 1, 0)} books.`,
            meta: "Ready",
          },
          ...current.activityEvents,
        ],
      }));
    } catch (error) {
      pushError("Load failed", String(error));
    } finally {
      setBusyLabel("");
    }
  }

  async function runOptimize() {
    setBusyLabel("Optimizing vocabulary");
    setState((current) => ({
      ...current,
      processing: true,
      activityEvents: [
        {
          phase: "thinking",
          title: "Optimization started",
          message: "Local statistics and model enrichment are preparing production cards.",
          meta: "Pipeline",
        },
        ...current.activityEvents,
      ],
    }));
    try {
      const result = await callBackend<OptimizeResult>("optimize", { entries: filteredEntries });
      setState((current) => ({
        ...current,
        processing: false,
        statusMessage: `${result.accepted_new} cards added to optimized.tsv`,
        activityEvents: [
          ...(result.events ?? []),
          {
            phase: "answered",
            title: "Optimization complete",
            message: `Processed ${result.processed_new}; accepted ${result.accepted_new}; skipped ${result.skipped_existing}.`,
            meta: result.tsv_path,
          },
          ...current.activityEvents,
        ],
      }));
    } catch (error) {
      pushError("Optimization failed", String(error));
    } finally {
      setBusyLabel("");
    }
  }

  async function runExport(format: "anki" | "quizlet") {
    setBusyLabel(`Exporting ${format}`);
    try {
      const result = await callBackend<{ path: string }>("export", { format, entries: filteredEntries });
      setState((current) => ({
        ...current,
        statusMessage: `Export saved: ${result.path}`,
        activityEvents: [
          {
            phase: "answered",
            title: `${format.toUpperCase()} export`,
            message: `${filteredEntries.length} rows exported.`,
            meta: result.path,
          },
          ...current.activityEvents,
        ],
      }));
    } catch (error) {
      pushError("Export failed", String(error));
    } finally {
      setBusyLabel("");
    }
  }

  function pushError(title: string, message: string) {
    setState((current) => ({
      ...current,
      processing: false,
      statusMessage: title,
      activityEvents: [{ phase: "failed", title, message, meta: "Error" }, ...current.activityEvents],
    }));
  }

  return (
    <main className="premium-grid relative h-full overflow-hidden bg-[#03111f] text-foreground">
      <div className="relative grid h-full grid-cols-[280px_minmax(0,1fr)_360px] gap-5 p-5">
        <Sidebar state={state} onScan={() => runLoad("scan")} onDemo={() => runLoad("load_demo")} />
        <section className="flex min-w-0 flex-col gap-5">
          <Header state={state} filteredCount={filteredEntries.length} busyLabel={busyLabel} />
          <Toolbar
            state={state}
            setState={setState}
            onOptimize={runOptimize}
            onExport={runExport}
            filteredCount={filteredEntries.length}
          />
          <Metrics state={state} filteredCount={filteredEntries.length} />
          <VocabularyTable entries={filteredEntries} />
        </section>
        <ActivityPanel events={state.activityEvents} processing={state.processing} />
      </div>
    </main>
  );
}

function Sidebar({ state, onScan, onDemo }: { state: AppState; onScan: () => void; onDemo: () => void }) {
  return (
    <aside className="glass flex min-h-0 flex-col rounded-[28px] p-5">
      <div className="mb-8 flex items-center gap-3">
        <div className="grid h-11 w-11 place-items-center rounded-2xl bg-cyan-300/12 text-cyan-200 shadow-glow">
          <BookOpen size={22} />
        </div>
        <div>
          <div className="text-base font-semibold">Kindle Cards</div>
          <div className="text-xs text-muted-foreground">Vocabulary OS</div>
        </div>
      </div>

      <div className="mb-5 rounded-2xl border border-white/10 bg-white/[0.045] p-4">
        <div className="mb-1 text-sm font-semibold">{state.sourceName}</div>
        <div className="line-clamp-2 text-xs leading-5 text-muted-foreground">{state.sourceStatus}</div>
      </div>

      <div className="space-y-2">
        <Button className="w-full justify-start" onClick={onScan} disabled={state.processing}>
          <RefreshCw size={16} />
          Проверить Kindle
        </Button>
        <Button className="w-full justify-start" variant="secondary" onClick={onDemo}>
          <FolderOpen size={16} />
          Preview data
        </Button>
      </div>

      <div className="mt-8 space-y-2">
        <NavItem icon={<Database size={16} />} label="Vocabulary" active />
        <NavItem icon={<Brain size={16} />} label="AI enrichment" />
        <NavItem icon={<BarChart3 size={16} />} label="Analytics" />
      </div>

      <div className="mt-auto rounded-2xl border border-cyan-300/15 bg-cyan-300/[0.06] p-4">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-cyan-100">
          <Sparkles size={15} />
          Premium pipeline
        </div>
        <p className="text-xs leading-5 text-muted-foreground">
          Local statistics, DeepSeek enrichment and export live in one designed workflow.
        </p>
      </div>
    </aside>
  );
}

function NavItem({ icon, label, active }: { icon: React.ReactNode; label: string; active?: boolean }) {
  return (
    <div
      className={`flex h-10 items-center gap-3 rounded-xl px-3 text-sm transition ${
        active ? "bg-white/[0.08] text-foreground" : "text-muted-foreground hover:bg-white/[0.05] hover:text-foreground"
      }`}
    >
      {icon}
      {label}
    </div>
  );
}

function Header({ state, filteredCount, busyLabel }: { state: AppState; filteredCount: number; busyLabel: string }) {
  return (
    <header className="flex items-start justify-between gap-4 pt-1">
      <div>
        <div className="mb-3 flex items-center gap-2">
          <Badge>2026 desktop workspace</Badge>
          {busyLabel ? <Badge className="border-amber-200/20 bg-amber-200/10 text-amber-100">{busyLabel}</Badge> : null}
        </div>
        <h1 className="text-balance text-4xl font-semibold tracking-[-0.03em] text-white">Словарь</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">{state.statusMessage}</p>
      </div>
      <div className="rounded-2xl border border-white/10 bg-white/[0.055] px-4 py-3 text-right">
        <div className="text-2xl font-semibold">{filteredCount}</div>
        <div className="text-xs text-muted-foreground">visible cards</div>
      </div>
    </header>
  );
}

function Toolbar({
  state,
  setState,
  onOptimize,
  onExport,
  filteredCount,
}: {
  state: AppState;
  setState: React.Dispatch<React.SetStateAction<AppState>>;
  onOptimize: () => void;
  onExport: (format: "anki" | "quizlet") => void;
  filteredCount: number;
}) {
  return (
    <Card className="rounded-[24px] p-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[280px] flex-1">
          <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-11"
            placeholder="Поиск по слову, контексту или книге"
            value={state.searchText}
            onChange={(event) => setState((current) => ({ ...current, searchText: event.target.value }))}
          />
        </div>
        <Select
          className="w-[240px]"
          value={String(state.selectedBookIndex)}
          onChange={(event) => setState((current) => ({ ...current, selectedBookIndex: Number(event.target.value) }))}
        >
          {state.books.map((book, index) => (
            <option key={`${book.key}-${index}`} value={index}>
              {book.label}
            </option>
          ))}
        </Select>
        <Button variant="secondary" className="shrink-0" onClick={() => onExport("anki")} disabled={!filteredCount || state.processing}>
          <Download size={16} />
          Anki
        </Button>
        <Button variant="secondary" className="shrink-0" onClick={() => onExport("quizlet")} disabled={!filteredCount || state.processing}>
          <FileDown size={16} />
          Quizlet
        </Button>
        <Button className="shrink-0" onClick={onOptimize} disabled={!filteredCount || state.processing}>
          <Sparkles size={16} />
          Optimize
        </Button>
      </div>
    </Card>
  );
}

function Metrics({ state, filteredCount }: { state: AppState; filteredCount: number }) {
  return (
    <div className="grid grid-cols-3 gap-4">
      <Metric icon={<Languages />} label="Слов в выборке" value={filteredCount} />
      <Metric icon={<BookOpen />} label="Книг в базе" value={Math.max(state.books.length - 1, 0)} />
      <Metric icon={<Activity />} label="AI events" value={state.activityEvents.length} />
    </div>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <Card className="group overflow-hidden rounded-[24px] p-4 transition hover:-translate-y-0.5 hover:shadow-glow">
      <div className="flex items-center justify-between">
        <div className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
        <div className="grid h-9 w-9 place-items-center rounded-xl bg-cyan-300/10 text-cyan-200">{icon}</div>
      </div>
      <div className="mt-4 text-3xl font-semibold tracking-[-0.04em] text-white">{value}</div>
    </Card>
  );
}

function VocabularyTable({ entries }: { entries: VocabEntry[] }) {
  return (
    <Card className="min-h-0 flex-1 overflow-hidden rounded-[28px]">
      <div className="grid grid-cols-[140px_120px_minmax(180px,1fr)_170px] border-b border-white/10 bg-white/[0.035] px-5 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        <div>Word</div>
        <div>Stem</div>
        <div>Context</div>
        <div>Book</div>
      </div>
      <div className="h-[calc(100%-44px)] overflow-y-auto overflow-x-hidden">
        <AnimatePresence initial={false}>
          {entries.length ? (
            entries.map((entry, index) => (
              <motion.div
                key={`${entry.word}-${entry.looked_up_at}-${index}`}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.22, delay: Math.min(index * 0.012, 0.14) }}
                className="grid grid-cols-[140px_120px_minmax(180px,1fr)_170px] items-center gap-0 border-b border-white/[0.06] px-5 py-4 text-sm hover:bg-white/[0.035]"
              >
                <div className="font-semibold text-white">{entry.word}</div>
                <div className="text-muted-foreground">{entry.stem || "—"}</div>
                <div className="truncate text-muted-foreground">{entry.context || "No context"}</div>
                <div className="truncate text-muted-foreground">{entry.book_title || "Unknown"}</div>
              </motion.div>
            ))
          ) : (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="grid h-full place-items-center p-10">
              <div className="text-center">
                <div className="mx-auto mb-5 grid h-16 w-16 place-items-center rounded-3xl border border-white/10 bg-white/[0.055] text-muted-foreground">
                  <BookOpen size={30} />
                </div>
                <div className="text-lg font-semibold text-white">Здесь появятся сохраненные слова</div>
                <div className="mt-2 text-sm text-muted-foreground">Откройте vocab.db или подключите Kindle.</div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </Card>
  );
}

function ActivityPanel({ events, processing }: { events: ActivityEvent[]; processing: boolean }) {
  return (
    <aside className="glass flex min-h-0 flex-col rounded-[28px] p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-white">Activity</div>
          <div className="text-xs text-muted-foreground">Pipeline, AI reasoning, exports</div>
        </div>
        <Badge className={processing ? "border-amber-200/20 bg-amber-200/10 text-amber-100" : ""}>
          {processing ? "Running" : "Idle"}
        </Badge>
      </div>
      <Progress value={processing ? 62 : 100} className="mb-5" />
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overflow-x-hidden pr-1">
        {events.map((event, index) => (
          <motion.div
            key={`${event.title}-${index}`}
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.24, delay: Math.min(index * 0.015, 0.16) }}
            className={`min-w-0 rounded-2xl border p-4 ${
              event.phase === "failed"
                ? "border-rose-300/20 bg-rose-300/10"
                : event.phase === "answered"
                  ? "border-emerald-300/20 bg-emerald-300/10"
                  : "border-cyan-300/15 bg-cyan-300/[0.055]"
            }`}
          >
            <div className="mb-1 flex items-center justify-between gap-3">
              <div className="truncate text-sm font-semibold text-white">{event.title}</div>
              <div className="shrink-0 text-[11px] text-muted-foreground">{event.meta}</div>
            </div>
            <p className="line-clamp-4 text-xs leading-5 text-muted-foreground">{event.message}</p>
          </motion.div>
        ))}
      </div>
    </aside>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
