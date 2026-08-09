import { Moon, Sun } from "lucide-react";
import type { ThemeMode } from "../../store/app-store";
import { LobeIcon, HEADER_ICON_BLOCK } from "../../lib/icons";
import { iconButton } from "../../lib/ui";
import { cn } from "../../lib/cn";

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
      className={cn(iconButton)}
      style={{ width: HEADER_ICON_BLOCK, height: HEADER_ICON_BLOCK }}
      aria-label={`切换到${next === "dark" ? "深色" : "浅色"}主题`}
      onClick={() => onChange(next)}
    >
      {theme === "dark" ? (
        <LobeIcon icon={Sun} size="md" />
      ) : (
        <LobeIcon icon={Moon} size="md" />
      )}
    </button>
  );
}
