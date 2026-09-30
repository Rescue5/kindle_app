import * as React from "react";
import { Brain, Palette, ScrollText, Shield } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { callBackend } from "@/lib/backend";
import type { AppSettings } from "@/types";

type SettingsSectionProps = {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
};

function SettingsSection({ icon: Icon, title, children }: SettingsSectionProps) {
  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b border-line bg-panel-raised/40">
        <div className="flex items-center gap-2.5">
          <div className="grid h-8 w-8 place-items-center rounded-[8px] bg-secondary text-primary">
            <Icon size={16} />
          </div>
          <CardTitle>{title}</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">{children}</CardContent>
    </Card>
  );
}

type FieldProps = {
  label: string;
  hint?: string;
  children: React.ReactNode;
};

function Field({ label, hint, children }: FieldProps) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      {children}
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </label>
  );
}

type SettingsViewProps = {
  settings: AppSettings;
  onChange: (settings: AppSettings) => void;
};

export function SettingsView({ settings, onChange }: SettingsViewProps) {
  const [saving, setSaving] = React.useState(false);
  const [saveError, setSaveError] = React.useState("");

  async function persist(next: AppSettings) {
    onChange(next);
    setSaving(true);
    setSaveError("");
    try {
      await callBackend<{ saved: boolean }>("save_settings", { settings: next });
    } catch (error) {
      setSaveError(String(error));
    } finally {
      setSaving(false);
    }
  }

  function update<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
    const next = { ...settings, [key]: value };
    void persist(next);
  }

  React.useEffect(() => {
    const root = document.documentElement;
    const { theme } = settings;
    root.classList.remove("light", "dark");
    if (theme === "system") {
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      root.classList.add(prefersDark ? "dark" : "light");
    } else {
      root.classList.add(theme);
    }
  }, [settings.theme]);

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-background/35">
      <header className="flex-none border-b border-line px-6 py-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-[22px] font-semibold leading-7">Настройки</h1>
            <p className="mt-1 text-sm text-muted-foreground">Параметры приложения, LLM-обогащения и синхронизации с Obsidian</p>
          </div>
          {saving ? (
            <span className="text-xs text-muted-foreground">Сохранение…</span>
          ) : saveError ? (
            <span className="text-xs text-destructive">Ошибка сохранения: {saveError}</span>
          ) : null}
        </div>
      </header>
      <div className="app-scrollbar min-h-0 flex-1 space-y-5 overflow-y-auto p-6">
        <SettingsSection icon={Palette} title="Общие">
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Тема">
              <Select
                value={settings.theme}
                onChange={(event) => update("theme", event.target.value as AppSettings["theme"])}
              >
                <option value="system">Системная</option>
                <option value="light">Светлая</option>
                <option value="dark">Тёмная</option>
              </Select>
            </Field>
            <Field label="Язык интерфейса">
              <Select
                value={settings.language}
                onChange={(event) => update("language", event.target.value as AppSettings["language"])}
              >
                <option value="ru">Русский</option>
                <option value="en">English</option>
              </Select>
            </Field>
            <Field label="Формат экспорта по умолчанию">
              <Select
                value={settings.default_export_format}
                onChange={(event) =>
                  update("default_export_format", event.target.value as AppSettings["default_export_format"])
                }
              >
                <option value="anki">Anki</option>
                <option value="quizlet">Quizlet</option>
              </Select>
            </Field>
            <Field label="Папка данных приложения" hint="Относительный или абсолютный путь">
              <Input
                value={settings.app_data_path}
                onChange={(event) => update("app_data_path", event.target.value)}
                placeholder=".app-data"
              />
            </Field>
          </div>
        </SettingsSection>

        <SettingsSection icon={Brain} title="LLM-обогащение">
          <div className="flex items-start justify-between gap-4 rounded-[10px] border border-line bg-panel-raised/40 p-4">
            <div className="flex items-start gap-3">
              <div className="grid h-9 w-9 place-items-center rounded-[8px] bg-secondary text-primary">
                <Shield size={16} />
              </div>
              <div>
                <label htmlFor="llm-enabled-switch" className="text-sm font-medium">
                  Включить LLM-обогащение
                </label>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Использовать OpenAI-совместимый API для переводов и оттенков значения.
                </p>
              </div>
            </div>
            <Switch
              id="llm-enabled-switch"
              checked={settings.llm_enabled}
              onCheckedChange={(value) => update("llm_enabled", value)}
              aria-label="Включить LLM-обогащение"
            />
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Модель">
              <Input
                value={settings.llm_model}
                onChange={(event) => update("llm_model", event.target.value)}
                disabled={!settings.llm_enabled}
                placeholder="deepseek-v4-flash"
              />
            </Field>
            <Field label="Базовый URL" hint="OpenAI-совместимый endpoint">
              <Input
                value={settings.llm_base_url}
                onChange={(event) => update("llm_base_url", event.target.value)}
                disabled={!settings.llm_enabled}
                placeholder="https://api.dslab.tech/v1"
              />
            </Field>
          </div>
        </SettingsSection>

        <SettingsSection icon={ScrollText} title="Obsidian">
          <div
            className={`flex items-center justify-between gap-4 rounded-[10px] border px-4 py-3 text-sm ${
              settings.obsidian_sync_enabled
                ? "border-purple-700/25 bg-purple-700/5 text-purple-800"
                : "border-line bg-panel-raised/40 text-muted-foreground"
            }`}
          >
            <div className="flex items-center gap-2.5">
              <span className={`h-2 w-2 rounded-full ${settings.obsidian_sync_enabled ? "bg-purple-400" : "bg-muted-foreground"}`} />
              <div>
                <label htmlFor="obsidian-enabled-switch" className="font-medium">Синхронизация с Obsidian</label>
                <p className="mt-0.5 text-xs opacity-75">Добавлять подходящие слова из библиотеки в Obsidian.</p>
              </div>
            </div>
            <Switch
              id="obsidian-enabled-switch"
              checked={settings.obsidian_sync_enabled}
              onCheckedChange={(value) => update("obsidian_sync_enabled", value)}
              aria-label="Включить синхронизацию с Obsidian"
            />
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Путь к хранилищу Obsidian" hint="Абсолютный путь до папки vault">
              <Input
                value={settings.obsidian_vault_path}
                onChange={(event) => update("obsidian_vault_path", event.target.value)}
                placeholder="/Users/…/Documents/Obsidian Vault"
              />
            </Field>
            <Field label="Папка для карточек" hint="Папка внутри vault">
              <Input
                value={settings.obsidian_cards_path}
                onChange={(event) => update("obsidian_cards_path", event.target.value)}
                placeholder="Kindle Cards"
              />
            </Field>
          </div>
          <div className="flex items-center gap-3 rounded-[10px] border border-line bg-panel-raised/40 p-3 transition hover:bg-panel-raised">
            <Switch
              id="obsidian-backup-switch"
              checked={settings.obsidian_backup_enabled}
              onCheckedChange={(value) => update("obsidian_backup_enabled", value)}
              aria-label="Создавать резервную копию"
            />
            <div>
              <label htmlFor="obsidian-backup-switch" className="text-sm font-medium">
                Создавать резервную копию
              </label>
              <p className="text-xs text-muted-foreground">Перед синхронизацией сохранить текущее состояние папки карточек.</p>
            </div>
          </div>
        </SettingsSection>
      </div>
    </div>
  );
}
