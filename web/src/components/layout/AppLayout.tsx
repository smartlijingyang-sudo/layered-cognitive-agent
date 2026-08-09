import { Menu, PanelLeftClose, PanelLeft, Sparkles, X } from "lucide-react";
import type { ThemeMode } from "../../store/app-store";
import type { Verbosity } from "../../projectors";
import { cn } from "../../lib/cn";
import { focusRing } from "../../lib/ui";

export function AppLayout({
  theme: _theme,
  onThemeChange: _onThemeChange,
  llmAvailable: _llmAvailable,
  developerMode: _developerMode,
  onDeveloperModeChange: _onDeveloperModeChange,
  verbosity: _verbosity,
  onVerbosityChange: _onVerbosityChange,
  sidebar,
  main,
  tracePanel,
  sidebarOpen,
  onSidebarToggle,
  chatTitle,
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
  readonly chatTitle?: string;
}) {
  void _theme;
  void _onThemeChange;
  void _llmAvailable;
  void _developerMode;
  void _onDeveloperModeChange;
  void _verbosity;
  void _onVerbosityChange;

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg)] text-[var(--text)]">
      {/* Mobile overlay */}
      {sidebarOpen ? (
        <button
          type="button"
          aria-label="关闭侧栏遮罩"
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[2px] md:hidden"
          onClick={onSidebarToggle}
        />
      ) : null}

      {/* Sidebar — LobeHub left nav */}
      <aside
        className={cn(
          "flex shrink-0 flex-col border-r border-[var(--border-subtle)] bg-[var(--sidebar-bg)]",
          "fixed inset-y-0 left-0 z-50 w-[min(var(--sidebar-width),88vw)] transition-transform duration-200",
          "md:static md:z-auto md:w-[var(--sidebar-width)] md:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full md:hidden",
        )}
      >
        <div className="flex items-center justify-between gap-2 border-b border-[var(--border-subtle)] px-3 py-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <span
              className={cn(
                "inline-flex size-8 shrink-0 items-center justify-center rounded-[var(--radius-md)]",
                "bg-[var(--fill-hover)] text-[var(--text)]",
              )}
            >
              <Sparkles size={15} strokeWidth={2} />
            </span>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold tracking-tight">LCA</div>
              <div className="truncate text-[11px] text-[var(--text-faint)]">团队协作</div>
            </div>
          </div>
          <button
            type="button"
            className={cn(
              "inline-flex cursor-pointer items-center justify-center rounded-[var(--radius-md)] p-1.5",
              "text-[var(--text-muted)] hover:bg-[var(--fill-hover)] md:hidden",
              focusRing,
            )}
            aria-label="关闭侧栏"
            onClick={onSidebarToggle}
          >
            <X size={16} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">{sidebar}</div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header
          className={cn(
            "flex h-12 shrink-0 items-center gap-2 border-b border-[var(--border-subtle)] px-3",
            "bg-[var(--header-bg)] backdrop-blur-md md:px-4",
          )}
        >
          <button
            type="button"
            className={cn(
              "inline-flex cursor-pointer items-center justify-center rounded-[var(--radius-md)] p-1.5",
              "text-[var(--text-muted)] hover:bg-[var(--fill-hover)]",
              focusRing,
            )}
            aria-label={sidebarOpen ? "收起侧栏" : "打开侧栏"}
            onClick={onSidebarToggle}
          >
            <span className="md:hidden">
              {sidebarOpen ? <X size={16} /> : <Menu size={16} />}
            </span>
            <span className="hidden md:inline">
              {sidebarOpen ? <PanelLeftClose size={16} /> : <PanelLeft size={16} />}
            </span>
          </button>
          <h1 className="m-0 min-w-0 flex-1 truncate text-sm font-medium text-[var(--text)]">
            {chatTitle || "新对话"}
          </h1>
        </header>

        <div
          className={cn(
            "grid min-h-0 flex-1",
            tracePanel ? "lg:grid-cols-[minmax(0,1fr)_minmax(280px,340px)]" : "grid-cols-1",
          )}
        >
          <div className="flex min-h-0 min-w-0 flex-col">{main}</div>
          {tracePanel ? (
            <div
              className={cn(
                "hidden min-h-0 overflow-auto border-l border-[var(--border-subtle)]",
                "bg-[var(--surface-secondary)] p-3 lg:block",
              )}
            >
              {tracePanel}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
