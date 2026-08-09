import {
  ChevronRight,
  Home,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  X,
} from "lucide-react";
import type { ThemeMode } from "../../store/app-store";
import type { Verbosity } from "../../projectors";
import { cn } from "../../lib/cn";
import { LobeIcon, HEADER_ICON_BLOCK } from "../../lib/icons";
import { iconButton } from "../../lib/ui";
import { AgentAvatar } from "../shared/AgentAvatar";

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
  homeActive,
  onHome,
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
  /** Home view: right panel shows welcome, no topic selected. */
  readonly homeActive?: boolean;
  readonly onHome?: () => void;
}) {
  void _theme;
  void _onThemeChange;
  void _llmAvailable;
  void _developerMode;
  void _onDeveloperModeChange;
  void _verbosity;
  void _onVerbosityChange;

  return (
    <div className="lobe-app-shell flex h-screen overflow-hidden bg-[var(--bg)] text-[var(--text)]">
      {sidebarOpen ? (
        <button
          type="button"
          aria-label="关闭侧栏遮罩"
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[3px] transition-opacity md:hidden"
          onClick={onSidebarToggle}
        />
      ) : null}

      <aside
        className={cn(
          "lobe-sidebar flex shrink-0 flex-col bg-[var(--sidebar-bg)]",
          "border-r border-[var(--border-subtle)]",
          "fixed inset-y-0 left-0 z-50 w-[min(var(--sidebar-width),88vw)]",
          "transition-transform duration-200 ease-[cubic-bezier(0.4,0,0.2,1)]",
          "md:static md:z-auto md:w-[var(--sidebar-width)] md:translate-x-0",
          sidebarOpen
            ? "translate-x-0 shadow-[var(--shadow-popover)] md:shadow-none"
            : "-translate-x-full md:hidden",
        )}
      >
        {/* LobeHub SideBarHeaderLayout: Home icon breadcrumb + panel toggle */}
        <div className="flex shrink-0 items-center justify-between gap-1 px-1.5 py-2">
          <div className="flex min-w-0 flex-1 items-center gap-0.5 px-1">
            <button
              type="button"
              className={cn(
                iconButton,
                homeActive && "bg-[var(--fill-hover)] text-[var(--text)]",
              )}
              style={{ width: HEADER_ICON_BLOCK, height: HEADER_ICON_BLOCK }}
              aria-label="首页"
              aria-current={homeActive ? "page" : undefined}
              onClick={onHome}
              title="首页"
            >
              <LobeIcon icon={Home} size="md" />
            </button>
            <LobeIcon
              icon={ChevronRight}
              size="xs"
              className="shrink-0 text-[var(--text-faint)]"
            />
            <span className="truncate px-1 text-[12px] text-[var(--text-muted)]">
              {homeActive ? "首页" : "对话"}
            </span>
          </div>
          <button
            type="button"
            className={cn(iconButton, "md:hidden")}
            style={{ width: HEADER_ICON_BLOCK, height: HEADER_ICON_BLOCK }}
            aria-label="关闭侧栏"
            onClick={onSidebarToggle}
          >
            <LobeIcon icon={X} size="md" />
          </button>
        </div>

        <div className="lobe-sidebar-scroll min-h-0 flex-1 overflow-y-auto px-2 pb-2">
          {sidebar}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Address / title bar with agent avatar (LobeHub conversation header) */}
        <header
          className={cn(
            "lobe-header flex h-12 shrink-0 items-center gap-1.5 px-2 md:px-3",
            "border-b border-[var(--border-subtle)]",
            "bg-[var(--header-bg)] backdrop-blur-xl backdrop-saturate-150",
          )}
        >
          <button
            type="button"
            className={iconButton}
            style={{ width: HEADER_ICON_BLOCK, height: HEADER_ICON_BLOCK }}
            aria-label={sidebarOpen ? "收起侧栏" : "打开侧栏"}
            onClick={onSidebarToggle}
          >
            <span className="md:hidden">
              {sidebarOpen ? (
                <LobeIcon icon={X} size="md" />
              ) : (
                <LobeIcon icon={Menu} size="md" />
              )}
            </span>
            <span className="hidden md:inline">
              {sidebarOpen ? (
                <LobeIcon icon={PanelLeftClose} size="md" />
              ) : (
                <LobeIcon icon={PanelLeftOpen} size="md" />
              )}
            </span>
          </button>

          {/* Title pill with avatar */}
          <div
            className={cn(
              "flex min-w-0 flex-1 items-center gap-2 rounded-[var(--radius-md)]",
              "px-1.5 py-1 md:max-w-xl",
            )}
          >
            <AgentAvatar size={32} title="LCA" />
            <div className="min-w-0 flex-1">
              <h1 className="m-0 truncate text-[13px] font-medium tracking-tight text-[var(--text)]">
                {homeActive ? "LCA" : chatTitle || "新话题"}
              </h1>
              <p className="m-0 truncate text-[11px] text-[var(--text-faint)]">
                {homeActive ? "首页" : "助手"}
              </p>
            </div>
          </div>
        </header>

        <div
          className={cn(
            "grid min-h-0 flex-1",
            tracePanel ? "lg:grid-cols-[minmax(0,1fr)_minmax(300px,360px)]" : "grid-cols-1",
          )}
        >
          <div className="flex min-h-0 min-w-0 flex-col">{main}</div>
          {tracePanel ? (
            <aside
              className={cn(
                "hidden min-h-0 overflow-auto border-l border-[var(--border-subtle)]",
                "bg-[var(--surface-secondary)] p-3 lg:block",
              )}
            >
              {tracePanel}
            </aside>
          ) : null}
        </div>
      </div>
    </div>
  );
}
