import { Menu, X, Sparkles } from "lucide-react";
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
    <div className="flex h-screen flex-col overflow-hidden bg-bg text-text">
      <header
        className={cn(
          "relative z-[60] flex shrink-0 items-center justify-between gap-4 border-b border-border/70 px-4 py-2.5 backdrop-blur-md md:px-5",
        )}
        style={{ background: "var(--header-bg)" }}
      >
        <div className="flex items-center gap-3">
          <button
            type="button"
            className={cn(
              "inline-flex cursor-pointer items-center justify-center rounded-[var(--radius-md)] p-2 text-text-muted hover:bg-surface-elevated md:hidden",
              focusRing,
            )}
            aria-label={sidebarOpen ? "关闭侧栏" : "打开侧栏"}
            onClick={onSidebarToggle}
          >
            {sidebarOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
          <div className="flex items-center gap-2.5">
            <span className="inline-flex size-8 items-center justify-center rounded-[var(--radius-md)] bg-accent/15 text-accent">
              <Sparkles size={16} />
            </span>
            <div>
              <h1 className="m-0 text-[0.9375rem] font-semibold tracking-tight">LCA</h1>
              <p className={cn("m-0 text-xs", mutedText)}>团队协作对话</p>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2.5 md:gap-3">
          <LlmBadge available={llmAvailable} />
          <label className="hidden items-center gap-2 text-xs sm:inline-flex">
            <span className={mutedText}>开发者</span>
            <Switch.Root
              className={cn(
                "relative h-5 w-9 rounded-full bg-border data-[state=checked]:bg-accent",
                focusRing,
              )}
              checked={developerMode}
              onCheckedChange={onDeveloperModeChange}
            >
              <Switch.Thumb
                className={cn(
                  "block size-4 translate-x-0.5 rounded-full bg-white shadow-sm transition-transform duration-200",
                  "data-[state=checked]:translate-x-[18px]",
                )}
              />
            </Switch.Root>
          </label>
          <label className="hidden items-center gap-2 text-xs md:inline-flex">
            <span className={mutedText}>详细度</span>
            <select
              className={cn(inputField, "w-auto min-w-[6.5rem] py-1 text-xs")}
              value={verbosity}
              onChange={(e) => onVerbosityChange(e.target.value as Verbosity)}
            >
              <option value="minimal">简洁</option>
              <option value="standard">标准</option>
              <option value="verbose">完整</option>
            </select>
          </label>
          <ThemeToggle theme={theme} onChange={onThemeChange} />
        </div>
      </header>

      {sidebarOpen ? (
        <button
          type="button"
          aria-label="关闭侧栏遮罩"
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[2px] md:hidden"
          onClick={onSidebarToggle}
        />
      ) : null}

      <div
        className={cn(
          "grid min-h-0 flex-1 grid-cols-1",
          tracePanel
            ? "lg:grid-cols-[260px_minmax(0,1fr)_minmax(280px,340px)]"
            : "md:grid-cols-[260px_minmax(0,1fr)]",
        )}
      >
        <div
          className={cn(
            "overflow-auto border-r border-border/70 bg-surface p-3",
            "fixed inset-y-0 left-0 z-50 w-[min(280px,88vw)] pt-[3.75rem] shadow-2xl transition-transform duration-200 md:shadow-none",
            "md:static md:z-auto md:w-auto md:pt-3",
            sidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
          )}
        >
          {sidebar}
        </div>
        <div className="flex min-h-0 min-w-0 flex-col">{main}</div>
        {tracePanel ? (
          <div className="hidden min-h-0 overflow-auto border-l border-border/70 bg-surface p-3 lg:block">
            {tracePanel}
          </div>
        ) : null}
      </div>
    </div>
  );
}
