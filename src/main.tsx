import * as React from "react";
import ReactDOM from "react-dom/client";
import { BarChart3, BookOpen, Library, Settings, Upload } from "lucide-react";
import { SettingsView } from "@/components/settings-view";
import { LibraryWorkspace } from "@/features/library/library-workspace";
import { useLibraryController } from "@/features/library/use-library-controller";
import "@/index.css";

type View = "library" | "settings";

const navigation = [
  { label: "Библиотека", icon: Library, view: "library" as const, enabled: true },
  { label: "Обработка", icon: BookOpen, view: "library" as const, enabled: false },
  { label: "Экспорты", icon: Upload, view: "library" as const, enabled: false },
  { label: "Аналитика", icon: BarChart3, view: "library" as const, enabled: false },
  { label: "Настройки", icon: Settings, view: "settings" as const, enabled: true },
];

function App() {
  const controller = useLibraryController();
  const [view, setView] = React.useState<View>("library");

  function changeView(next: View) {
    setView(next);
    if (next === "library") void controller.loadLibrary();
  }

  return (
    <div className="premium-grid flex h-full min-h-[620px] w-full overflow-hidden text-foreground">
      <aside className="flex w-[168px] flex-none flex-col border-r border-line bg-background/70 px-3 py-4">
        <div className="flex h-9 items-center gap-2.5 px-2 text-sm font-semibold">
          <BookOpen size={18} className="text-primary" />
          <span>Kindle Cards</span>
        </div>

        <nav className="mt-6 space-y-1" aria-label="Основная навигация">
          {navigation.map((item) => {
            const Icon = item.icon;
            const active = item.enabled && view === item.view && (item.view !== "library" || item.label === "Библиотека");
            return (
              <button
                key={item.label}
                type="button"
                disabled={!item.enabled}
                onClick={() => item.enabled && changeView(item.view)}
                className={`flex h-9 w-full items-center gap-2.5 rounded-[7px] px-2.5 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/45 ${
                  active
                    ? "bg-secondary text-foreground"
                    : item.enabled
                      ? "text-muted-foreground hover:bg-secondary/55 hover:text-foreground active:bg-secondary/75"
                      : "cursor-not-allowed text-muted-foreground/40"
                }`}
              >
                <Icon size={15} />
                {item.label}
              </button>
            );
          })}
        </nav>

        <div className="mt-auto border-t border-line px-2 pt-3 text-[11px] leading-5 text-muted-foreground">
          <div className="flex items-center justify-between"><span>Леммы</span><span className="tabular-nums text-foreground/80">{controller.entries.length}</span></div>
          <div className="flex items-center justify-between"><span>Новые</span><span className="tabular-nums text-foreground/80">{controller.entries.filter((entry) => entry.freshness === "new").length}</span></div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {view === "library" ? (
          <LibraryWorkspace controller={controller} />
        ) : (
          <SettingsView settings={controller.settings} onChange={controller.setSettings} />
        )}
      </div>
    </div>
  );
}

const rootElement = document.getElementById("root")!;
const rootState = rootElement as typeof rootElement & { __kindleCardsRoot?: ReturnType<typeof ReactDOM.createRoot> };
rootState.__kindleCardsRoot ??= ReactDOM.createRoot(rootElement);
rootState.__kindleCardsRoot.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
