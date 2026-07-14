import * as React from "react";
import { callBackend, cancelBackend, defaultSettings, listenProgress } from "@/lib/backend";
import {
  filterLexemes,
  idleOperation,
  kindleSignature,
  KINDLE_PROBE_INTERVAL_MS,
  shouldAutoSyncKindle,
  type QuickFilter,
} from "./domain";
import type {
  AppSettings,
  BookOption,
  ConnectorStatus,
  LexemeRecord,
  LibraryResult,
  Operation,
  ProgressEvent,
  QueueStatus,
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
  queue_status: QueueStatus;
  message?: string;
};

type ObsidianResult = {
  added: number;
  skipped: number;
  entries: LexemeRecord[];
  queue_status: QueueStatus;
};

const emptyQueue: QueueStatus = { pending: 0, processing: 0, failed: 0, total: 0 };

function jobId() {
  return typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `job-${Date.now()}`;
}

export function useLibraryController() {
  const [entries, setEntries] = React.useState<LexemeRecord[]>([]);
  const [books, setBooks] = React.useState<BookOption[]>([{ label: "Все книги", key: "" }]);
  const [connectors, setConnectors] = React.useState<ConnectorStatus>(unknownConnectors);
  const [settings, setSettings] = React.useState<AppSettings>(defaultSettings);
  const [query, setQuery] = React.useState("");
  const [debouncedQuery, setDebouncedQuery] = React.useState("");
  const debounceRef = React.useRef<number | null>(null);
  React.useEffect(() => {
    debounceRef.current = window.setTimeout(() => setDebouncedQuery(query), 180);
    return () => {
      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
    };
  }, [query]);
  const [selectedBookKey, setSelectedBookKey] = React.useState("");
  const [quickFilter, setQuickFilter] = React.useState<QuickFilter>("all");
  const [selectedId, setSelectedId] = React.useState("");
  const [operation, setOperation] = React.useState<Operation>(idleOperation);
  const [queueStatus, setQueueStatus] = React.useState<QueueStatus>(emptyQueue);
  const [loading, setLoading] = React.useState(true);
  const operationRef = React.useRef(operation);
  operationRef.current = operation;
  const prevConnectorsRef = React.useRef<ConnectorStatus>(unknownConnectors);
  const lastAutoSyncSignatureRef = React.useRef<string | null>(null);
  const lastAutoSyncAttemptAtRef = React.useRef(0);
  const probeInFlightRef = React.useRef(false);
  const autoSyncInFlightRef = React.useRef(false);
  const processingInFlightRef = React.useRef(false);
  const syncKindleRef = React.useRef(syncKindlePlaceholder);
  function syncKindlePlaceholder() { return Promise.resolve(); }

  const selectedBook = React.useMemo(
    () => books.find((book) => book.key === selectedBookKey) ?? books[0],
    [books, selectedBookKey],
  );
  const visibleEntries = React.useMemo(
    () => filterLexemes(entries, debouncedQuery, selectedBook, quickFilter),
    [entries, debouncedQuery, selectedBook, quickFilter],
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
    setQueueStatus(result.queueStatus ?? emptyQueue);
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

  const lastProbedAt = React.useRef(0);
  const probeConnectors = React.useCallback(async (force = false) => {
    if (document.visibilityState !== "visible") return;
    const now = Date.now();
    if (!force && now - lastProbedAt.current < KINDLE_PROBE_INTERVAL_MS) return;
    if (probeInFlightRef.current) return;
    probeInFlightRef.current = true;
    lastProbedAt.current = now;
    const previous = prevConnectorsRef.current;
    try {
      const status = await callBackend<ConnectorStatus>("connector_status", {});
      prevConnectorsRef.current = status;
      setConnectors(status);
      const kindle = status.kindle;
      const shouldSync = shouldAutoSyncKindle({
        previous: previous.kindle,
        current: kindle,
        lastSyncedSignature: lastAutoSyncSignatureRef.current,
        lastAttemptAt: lastAutoSyncAttemptAtRef.current,
        now,
      });
      if (shouldSync && operationRef.current.status !== "running" && !autoSyncInFlightRef.current) {
        lastAutoSyncAttemptAtRef.current = now;
        autoSyncInFlightRef.current = true;
        void syncKindleRef.current().finally(() => {
          autoSyncInFlightRef.current = false;
        });
      }
    } catch {
      setConnectors((current) => ({ ...current, kindle: { ...current.kindle, state: "error", checked_at: new Date().toISOString() } }));
    } finally {
      probeInFlightRef.current = false;
    }
  }, []);

  React.useEffect(() => {
    void probeConnectors();
    const interval = window.setInterval(() => void probeConnectors(), KINDLE_PROBE_INTERVAL_MS);
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
    lastAutoSyncAttemptAtRef.current = Date.now();
    const id = begin("kindle", "Синхронизация Kindle", "Проверяем подключение устройства");
    try {
      const result = await callBackend<LibraryResult>("sync_kindle", { job_id: id });
      applyLibrary(result);
      const connected = result.connectors.kindle.state === "connected";
      const signature = kindleSignature(result.connectors.kindle);
      if (connected && signature) {
        lastAutoSyncSignatureRef.current = signature;
      }
      setOperation((current) => ({
        ...current,
        status: connected ? "completed" : "error",
        stage: connected ? "completed" : "failed",
        title: connected ? "Kindle синхронизирован" : "Kindle не подключён",
        message: connected ? `В библиотеке ${result.entries.length} лемм` : "Локальная библиотека сохранена; подключите Kindle по USB",
        error: connected ? "" : "Устройство не найдено",
      }));
    } catch (error) {
      fail(id, "Синхронизация Kindle остановлена", error);
    } finally {
      void probeConnectors(true);
    }
  }, [applyLibrary, begin, fail, probeConnectors]);
  syncKindleRef.current = syncKindle;

  const processQueue = React.useCallback(async () => {
    if (processingInFlightRef.current) return;
    processingInFlightRef.current = true;
    const queueSize = queueStatus.pending + queueStatus.failed;
    const id = begin("processing", "Offline-обработка", `В очереди ${queueSize} лемм`);
    try {
      const result = await callBackend<ProcessingResult>("process_queue", { job_id: id });
      setEntries(result.entries);
      setQueueStatus(result.queue_status ?? emptyQueue);
      const skipped = result.skipped_existing ?? 0;
      const defaultMessage = skipped > 0
        ? `Обработано: ${result.processed_new}; принято: ${result.accepted_new}; отклонено: ${result.rejected_new}; пропущено ранее: ${skipped}`
        : `Обработано: ${result.processed_new}; принято: ${result.accepted_new}; отклонено: ${result.rejected_new}`;
      setOperation((current) => ({ ...current, status: "completed", stage: "completed", title: "Обработка завершена", message: result.message || defaultMessage, current: queueSize, total: queueSize }));
    } catch (error) {
      void loadLibrary();
      fail(id, "Offline-обработка остановлена", error);
    } finally {
      processingInFlightRef.current = false;
    }
  }, [begin, fail, loadLibrary, queueStatus.failed, queueStatus.pending]);

  React.useEffect(() => {
    const pending = queueStatus.pending + queueStatus.failed;
    if (loading || pending === 0 || processingInFlightRef.current) return;
    if (["running", "error", "cancelled"].includes(operation.status)) return;
    void processQueue();
  }, [loading, operation.status, processQueue, queueStatus.failed, queueStatus.pending]);

  const syncObsidian = React.useCallback(async () => {
    const id = begin("obsidian", "Синхронизация Obsidian", "Сверяем глобальную очередь карточек");
    try {
      const result = await callBackend<ObsidianResult>("sync_obsidian", { job_id: id });
      setEntries(result.entries);
      setQueueStatus(result.queue_status ?? emptyQueue);
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
    if (kind === "processing") return void processQueue();
    if (kind === "obsidian") return void syncObsidian();
    if (kind === "export") return void exportVisible(settings.default_export_format);
  }, [exportVisible, processQueue, settings.default_export_format, syncKindle, syncObsidian]);

  const dismissOperation = React.useCallback(() => setOperation(idleOperation), []);

  return React.useMemo(
    () => ({
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
      queueStatus,
      loading,
      syncKindle,
      syncObsidian,
      exportVisible,
      cancel,
      retry,
      dismissOperation,
      loadLibrary,
    }),
    [
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
      queueStatus,
      loading,
      syncKindle,
      syncObsidian,
      exportVisible,
      cancel,
      retry,
      dismissOperation,
      loadLibrary,
    ],
  );
}
