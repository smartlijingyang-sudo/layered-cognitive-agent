import { Menu, X } from "lucide-react";
import * as Switch from "@radix-ui/react-switch";
import { LlmBadge } from "../shared/LlmBadge";
import { ThemeToggle } from "../shared/ThemeToggle";
import type { ThemeMode } from "../../store/app-store";
import type { Verbosity } from "../../projectors";
import { cn } from "../../lib/cn";
import { focusRing, inputField, mutedText } from "../../lib/ui";

export function AppLayout({
  theme,
  onThemeChange,
  llmAvailable,
  developerMode,
  onDeveloperModeChange,
  verbosity,
  onVerbosityChange,
  sidebar,
  main,
  tracePanel,
  sidebarOpen,
  onSidebarToggle,
}: {
  readonly theme: ThemeMode;
  readonly onThemeChange: (theme: ThemeMode) => void;
  readonly llmAvailable: boolean | null;
  readonly developerMode: boolean;
  readonly onDeveloperModeChange: (enabled: boolean) => void;
  readonly verbosity: Verbosity;
  readonly onVerbosityChange: (verbosity: Verbosity) => void;
  readonly sidebar: React.ReactNode;
  readonly main: React.ReactNode;
  readonly tracePanel: React.ReactNode | null;
  readonly sidebarOpen: boolean;
  readonly onSidebarToggle: () => void;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-bg text-text">
      <header className="relative z-[60] flex items-center justify-between gap-4 border-b border-border bg-surface px-4 py-3 md:px-5">
        <div className="flex items-center gap-3">
          <button
            type="button"
            className={cn(
              "inline-flex cursor-pointer items-center justify-center rounded-[var(--radius-md)] border border-border p-2 md:hidden",
              focusRing,
            )}
            aria-label={sidebarOpen ? "关闭侧栏" : "打开侧栏"}
            onClick={onSidebarToggle}
          >
            {sidebarOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
          <div>
            <h1 className="m-0 text-lg font-semibold">LCA</h1>
            <p className={cn("m-0 text-sm", mutedText)}>团队协作可观测对话</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <LlmBadge available={llmAvailable} />
          <label className="inline-flex items-center gap-2 text-sm">
            <span className={mutedText}>开发者模式</span>
            <Switch.Root
              className={cn(
                "relative h-[22px] w-[38px] rounded-full bg-border data-[state=checked]:bg-accent",
                focusRing,
              )}
              checked={developerMode}
              onCheckedChange={onDeveloperModeChange}
            >
              <Switch.Thumb
                className={cn(
                  "block size-[18px] translate-x-0.5 rounded-full bg-white transition-transform duration-200",
                  "data-[state=checked]:translate-x-[18px]",
                )}
              />
            </Switch.Root>
          </label>
          <label className="inline-flex items-center gap-2 text-sm">
            <span className={mutedText}>Verbosity</span>
            <select
              className={cn(inputField, "w-auto min-w-[7rem] py-1.5 text-sm")}
              value={verbosity}
              onChange={(e) => onVerbosityChange(e.target.value as Verbosity)}
            >
              <option value="minimal">minimal</option>
              <option value="standard">standard</option>
              <option value="verbose">verbose</option>
            </select>
          </label>
          <ThemeToggle theme={theme} onChange={onThemeChange} />
        </div>
      </header>

      {sidebarOpen ? (
        <button
          type="button"
          aria-label="关闭侧栏遮罩"
          className="fixed inset-0 z-40 bg-black/45 md:hidden"
          onClick={onSidebarToggle}
        />
      ) : null}

      <div
        className={cn(
          "grid min-h-0 flex-1 grid-cols-1",
          tracePanel
            ? "lg:grid-cols-[240px_minmax(0,1fr)_minmax(280px,360px)] xl:grid-cols-[280px_minmax(0,1fr)_minmax(280px,360px)]"
            : "md:grid-cols-[240px_minmax(0,1fr)] lg:grid-cols-[280px_minmax(0,1fr)]",
        )}
      >
        <div
          className={cn(
            "overflow-auto border-r border-border bg-surface p-4",
            "fixed inset-y-0 left-0 z-50 w-[min(280px,85vw)] pt-[4.5rem] shadow-xl transition-transform duration-200",
            "md:static md:z-auto md:w-auto md:pt-4 md:shadow-none",
            sidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
          )}
        >
          {sidebar}
        </div>
        <main className="flex min-h-0 flex-col gap-4 overflow-auto p-4">{main}</main>
        {tracePanel ? (
          <div className="hidden min-h-0 overflow-auto border-l border-border bg-surface p-3 lg:block">
            {tracePanel}
          </div>
        ) : null}
      </div>
    </div>
  );
}
