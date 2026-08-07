import * as Switch from "@radix-ui/react-switch";
import { LlmBadge } from "../shared/LlmBadge";
import { ThemeToggle } from "../shared/ThemeToggle";
import type { ThemeMode } from "../../store/app-store";
import type { Verbosity } from "../../projectors";

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
}) {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>LCA</h1>
          <p className="muted">团队协作可观测对话</p>
        </div>
        <div className="header-actions">
          <LlmBadge available={llmAvailable} />
          <label className="dev-switch">
            <span>开发者模式</span>
            <Switch.Root
              className="switch-root"
              checked={developerMode}
              onCheckedChange={onDeveloperModeChange}
            >
              <Switch.Thumb className="switch-thumb" />
            </Switch.Root>
          </label>
          <label className="verbosity-select">
            <span>Verbosity</span>
            <select
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
      <div className={`app-grid ${tracePanel ? "with-trace" : ""}`}>
        {sidebar}
        <main className="main-column">{main}</main>
        {tracePanel}
      </div>
    </div>
  );
}
