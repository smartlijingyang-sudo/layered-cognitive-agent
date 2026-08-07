import { cn } from "./cn";

/** 复用的 Tailwind 类片段 —— 消费 design-tokens.css 语义变量。 */

export const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/45 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg)]";

export const inputField = cn(
  "w-full rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 text-[var(--text)]",
  "placeholder:text-[var(--text-muted)] disabled:cursor-not-allowed disabled:opacity-60",
  focusRing,
);

export const btnPrimary = cn(
  "inline-flex cursor-pointer items-center gap-1.5 rounded-[var(--radius-md)] border-0 px-3.5 py-2 font-semibold",
  "bg-[var(--accent)] text-teal-950 disabled:cursor-not-allowed disabled:opacity-50",
  focusRing,
);

export const btnSecondary = cn(
  "inline-flex cursor-pointer items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--border)]",
  "bg-transparent px-3.5 py-2 text-[var(--text)] disabled:cursor-not-allowed disabled:opacity-50",
  focusRing,
);

export const iconButton = cn(
  "inline-flex cursor-pointer items-center justify-center rounded-[var(--radius-md)] border border-[var(--border)]",
  "bg-transparent p-1.5 text-[var(--text-muted)] disabled:cursor-not-allowed disabled:opacity-50",
  focusRing,
);

export const mutedText = "text-[var(--text-muted)]";

export const panelSurface =
  "rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)]";

export const elevatedSurface =
  "rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)]";
