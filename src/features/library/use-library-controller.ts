import * as React from "react";
import { callBackend, cancelBackend, defaultSettings, listenProgress } from "@/lib/backend";
import { filterLexemes, idleOperation, processable, type QuickFilter } from "./domain";
import type {
  AppSettings,
  BookOption,
  ConnectorStatus,
  LexemeRecord,
  LibraryResult,
  Operation,
  ProgressEvent,
} from "@/types";

const unknownConnectors: ConnectorStatus = {
  kindle: { state: "unknown", label: "Kindle", checked_at: "" },
  obsidian: { state: "disabled", label: "Obsidian", checked_at: "" },
};

type ProcessingResult = {
  processed_new: number;
  accepted_new: number;
  rejected_new: number;
  skipped_existing: number;
  entries: LexemeRecord[];
};

type ObsidianResult = {
  added: number;
  skipped: number;
  entries: LexemeRecord[];
};

function jobId() {
  return typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `job-${Date.now()}`;
}

export function useLibraryController() {
  const [entries, setEntries] = React.useState<LexemeRecord[]>([]);
  const [books, setBooks] = React.useState<BookOption[]>([{ label: "Все книги", key: "" }]);
  const [connectors, setConnectors] = React.useState<ConnectorStatus>(unknownConnectors);
  const [settings, setSettings] = React.useState<AppSettings>(defaultSettings);
  const [query, setQuery] = React.useState("");
  const deferredQuery = React.useDeferredValue(query);
  const [selectedBookKey, setSelectedBookKey] = React.useState("");
  const [quickFilter, setQuickFilter] = React.useState<QuickFilter>("all");
  const [selectedId, setSelectedId] = React.useState("");
  const [operation, setOperation] = React.useState<Operation>(idleOperation);
  const [loading, setLoading] = React.useState(true);
  const operationRef = React.useRef(operation);
  operationRef.current = operation;

  const selectedBook = React.useMemo(
    () => books.find((book) => book.key === selectedBookKey) ?? books[0],
    [books, selectedBookKey],
  );
  const visibleEntries = React.useMemo(
    () => filterLexemes(entries, deferredQuery, selectedBook, quickFilter),
    [entries, deferredQuery, selectedBook, quickFilter],
  );
  const selectedEntry = React.useMemo(
    () => visibleEntries.find((entry) => entry.id === selectedId) ?? visibleEntries[0] ?? null,
    [visibleEntries, selectedId],
  );

  React.useEffect(() => {
    if (!selectedEntry) {
      setSelectedId("");
    } else if (selectedEntry.id !== selectedId) {
      setSelectedId(selectedEntry.id);
    }
  }, [selectedEntry, selectedId]);

  const applyLibrary = React.useCallback((result: LibraryResult) => {
    setEntries(result.entries);
    setBooks(result.books.length ? result.books : [{ label: "Все книги", key: "" }]);
    setConnectors((current) => ({
      kindle: result.connectors?.kindle?.state === "unknown" ? current.kindle : (result.connectors?.kindle ?? current.kindle),
      obsidian: result.connectors?.obsidian ?? current.obsidian,
    }));
  }, []);

  const loadLibrary = React.useCallback(async () => {
    const result = await callBackend<LibraryResult>("load_library", {});
    applyLibrary(result);
  }, [applyLibrary]);

  React.useEffect(() => {
    let cancelled = false;
    void Promise.all([callBackend<AppSettings>("load_settings", {}), callBackend<LibraryResult>("load_library", {})])
      .then(([loadedSettings, library]) => {
        if (cancelled) return;
        setSettings(loadedSettings);
        applyLibrary(library);
      })
      .catch((error) => {
        if (cancelled) return;
        setOperation({ ...idleOperation, status: "error", title: "Не удалось открыть библиотеку", message: String(error), error: String(error) });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [applyLibrary]);

  React.useEffect(() => {
    let unlisten: () => void = () => {};
    void listenProgress((progress: ProgressEvent) => {
      setOperation((current) => {
        if (current.id !== progress.job_id) return current;
        return {
          ...current,
          status: progress.stage === "completed" ? "completed" : "running",
          stage: progress.stage,
          message: progress.message,
          current: progress.current,
          total: progress.total,
        };
      });
    }).then((dispose) => {
      unlisten = dispose;
    });
    return () => unlisten();
  }, []);

  const probeConnectors = React.useCallback(async () => {
    if (document.visibilityState !== "visible") return;
    setConnectors((current) => ({ ...current, kindle: { ...current.kindle, state: "checking" } }));
    try {
      const status = await callBackend<ConnectorStatus>("connector_status", {});
      setConnectors(status);
    } catch {
      setConnectors((current) => ({ ...current, kindle: { ...current.kindle, state: "error", checked_at: new Date().toISOString() } }));
    }
  }, []);

  React.useEffect(() => {
    void probeConnectors();
    const interval = window.setInterval(() => void probeConnectors(), 5000);
    const onVisibility = () => {
      if (document.visibilityState === "visible") void probeConnectors();
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("focus", onVisibility);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("focus", onVisibility);
    };
  }, [probeConnectors]);

  const begin = React.useCallback((kind: Operation["kind"], title: string, message: string) => {
    const id = jobId();
    setOperation({ id, kind, status: "running", title, message, current: 0, total: 0, stage: "starting", error: "" });
    return id;
  }, []);

  const fail = React.useCallback((id: string, title: string, error: unknown) => {
    const message = String(error);
    const cancelled = message.toLocaleLowerCase("ru").includes("отменена");
    setOperation({
      id,
      kind: operationRef.current.kind,
      status: cancelled ? "cancelled" : "error",
      title: cancelled ? "Операция отменена" : title,
      message: cancelled ? "Дочерний процесс остановлен" : message,
      current: 0,
      total: 0,
      stage: cancelled ? "cancelled" : "failed",
      error: cancelled ? "" : message,
    });
  }, []);

  const syncKindle = React.useCallback(async () => {
    const id = begin("kindle", "Синхронизация Kindle", "Проверяем подключение устройства");
    try {
      const result = await callBackend<LibraryResult>("sync_kindle", { job_id: id });
      applyLibrary(result);
      const connected = result.connectors.kindle.state === "connected";
      setOperation((current) => ({ ...current, status: connected ? "completed" : "error", title: connected ? "Kindle синхронизирован" : "Kindle не подключён", message: connected ? `В библиотеке ${result.entries.length} лемм` : "Локальная библиотека сохранена; подключите Kindle по USB", error: connected ? "" : "Устройство не найдено" }));
    } catch (error) {
      fail(id, "Синхронизация Kindle остановлена", error);
    } finally {
      void probeConnectors();
    }
  }, [applyLibrary, begin, fail, probeConnectors]);

  const processVisible = React.useCallback(async () => {
    const candidates = processable(visibleEntries);
    if (!candidates.length) return;
    const ids = new Set(candidates.map((entry) => entry.id));
    setEntries((current) => current.map((entry) => (ids.has(entry.id) ? { ...entry, processing: { ...entry.processing, state: "processing", error: "" } } : entry)));
    const id = begin("processing", "Offline-обработка", `В очереди ${candidates.length} лемм`);
    try {
      const result = await callBackend<ProcessingResult>("process_lexemes", { job_id: id, ids: Array.from(ids) });
      setEntries(result.entries);
      setOperation((current) => ({ ...current, status: "completed", stage: "completed", title: "Обработка завершена", message: `Обработано: ${result.processed_new}; принято: ${result.accepted_new}; отклонено: ${result.rejected_new}`, current: candidates.length, total: candidates.length }));
    } catch (error) {
      const wasCancelled = String(error).toLocaleLowerCase("ru").includes("отменена");
      setEntries((current) => current.map((entry) => (ids.has(entry.id) && entry.processing.state === "processing" ? { ...entry, processing: { ...entry.processing, state: wasCancelled ? "pending" : "failed", error: wasCancelled ? "" : String(error) } } : entry)));
      fail(id, "Offline-обработка остановлена", error);
    }
  }, [begin, fail, visibleEntries]);

  const syncObsidian = React.useCallback(async () => {
    const id = begin("obsidian", "Синхронизация Obsidian", "Сверяем глобальную очередь карточек");
    try {
      const result = await callBackend<ObsidianResult>("sync_obsidian", { job_id: id });
      setEntries(result.entries);
      setOperation((current) => ({ ...current, status: "completed", stage: "completed", title: "Obsidian синхронизирован", message: `Добавлено: ${result.added}; без изменений или заблокировано: ${result.skipped}` }));
    } catch (error) {
      fail(id, "Синхронизация Obsidian остановлена", error);
    }
  }, [begin, fail]);

  const exportVisible = React.useCallback(async (format: "anki" | "quizlet") => {
    const candidates = visibleEntries.filter((entry) => entry.processing.state === "ready");
    if (!candidates.length) return;
    const id = begin("export", `Экспорт ${format === "anki" ? "Anki" : "Quizlet"}`, `Готовим ${candidates.length} лемм`);
    try {
      const result = await callBackend<{ path: string; exported: number }>("export", { job_id: id, format, entries: candidates });
      await loadLibrary();
      setOperation((current) => ({ ...current, status: "completed", stage: "completed", title: "Экспорт завершён", message: `Экспортировано: ${result.exported}. Файл: ${result.path}` }));
    } catch (error) {
      fail(id, "Экспорт остановлен", error);
    }
  }, [begin, fail, loadLibrary, visibleEntries]);

  const cancel = React.useCallback(async () => {
    const current = operationRef.current;
    if (!current.id || current.status !== "running") return;
    await cancelBackend(current.id);
    setOperation((value) => ({ ...value, status: "cancelled", title: "Операция отменена", message: "Дочерний процесс остановлен", stage: "cancelled" }));
  }, []);

  const retry = React.useCallback(() => {
    const kind = operationRef.current.kind;
    if (kind === "kindle") return void syncKindle();
    if (kind === "processing") return void processVisible();
    if (kind === "obsidian") return void syncObsidian();
    if (kind === "export") return void exportVisible(settings.default_export_format);
  }, [exportVisible, processVisible, settings.default_export_format, syncKindle, syncObsidian]);

  const dismissOperation = React.useCallback(() => setOperation(idleOperation), []);

  return {
    entries,
    books,
    connectors,
    settings,
    setSettings,
    query,
    setQuery,
    selectedBookKey,
    setSelectedBookKey,
    quickFilter,
    setQuickFilter,
    selectedId,
    setSelectedId,
    visibleEntries,
    selectedEntry,
    operation,
    loading,
    syncKindle,
    processVisible,
    syncObsidian,
    exportVisible,
    cancel,
    retry,
    dismissOperation,
    loadLibrary,
  };
}
