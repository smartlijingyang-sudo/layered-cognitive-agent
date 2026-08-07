import { Moon, Sun } from "lucide-react";
import type { ThemeMode } from "../../store/app-store";

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
      className="icon-button"
      aria-label={`切换到${next === "dark" ? "深色" : "浅色"}主题`}
      onClick={() => onChange(next)}
    >
      {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}
