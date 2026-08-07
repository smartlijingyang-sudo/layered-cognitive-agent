import { Moon, Sun } from "lucide-react";
import type { ThemeMode } from "../../store/app-store";
import { iconButton } from "../../lib/ui";

export function ThemeToggle({
  theme,
  onChange,
}: {
  readonly theme: ThemeMode;
  readonly onChange: (theme: ThemeMode) => void;
}) {
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      className={iconButton}
      aria-label={`切换到${next === "dark" ? "深色" : "浅色"}主题`}
      onClick={() => onChange(next)}
    >
      {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}
