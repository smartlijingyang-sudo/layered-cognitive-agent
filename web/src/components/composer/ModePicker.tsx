import type { ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import {
  ALL_MODES,
  AUTO_MODE_KEY,
  MODE_HAS_LEAD,
} from "../../contracts/modes.generated";
import { modeHelp, modeLabel } from "../../lib/modes";
import { ChevronDown, MessageCircle, X } from "lucide-react";
import { cn } from "../../lib/cn";
import { LobeIcon } from "../../lib/icons";
import { composerPill, elevatedSurface, focusRing, iconButton, mutedText } from "../../lib/ui";

export function ModePicker({
  value,
  onChange,
  disabled,
  variant = "mode",
  triggerId = "lca-mode-picker-trigger",
}: {
  readonly value: string;
  readonly onChange: (mode: string) => void;
  readonly disabled?: boolean;
  /** `mode` — action bar pill with mode name; `chat` — control bar "对话" row. */
  readonly variant?: "mode" | "chat";
  readonly triggerId?: string;
}) {
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <button
          type="button"
          id={triggerId}
          className={composerPill}
          disabled={disabled}
          title={modeHelp(value)}
        >
          {variant === "chat" ? (
            <>
              <LobeIcon icon={MessageCircle} size="sm" />
              <span className="truncate font-medium">对话</span>
            </>
          ) : (
            <span className="truncate font-medium">{modeLabel(value)}</span>
          )}
          <LobeIcon icon={ChevronDown} size="xs" className="shrink-0 opacity-60" />
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-[2px] animate-fade-in" />
        <Dialog.Content
          className={cn(
            elevatedSurface,
            "fixed top-1/2 left-1/2 z-50 max-h-[min(80vh,640px)] w-[min(560px,calc(100vw-2rem))]",
            "-translate-x-1/2 -translate-y-1/2 overflow-auto p-4 shadow-[var(--shadow-modal)]",
            "animate-fade-in",
            focusRing,
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <div>
              <Dialog.Title className="m-0 text-[15px] font-semibold tracking-tight">
                协作模式
              </Dialog.Title>
              <Dialog.Description className={cn("m-0 mt-0.5 text-xs", mutedText)}>
                选择团队如何协作完成任务
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button type="button" className={iconButton} aria-label="关闭">
                <LobeIcon icon={X} size="md" />
              </button>
            </Dialog.Close>
          </div>

          <div className="mt-4 grid gap-2">
            <ModeOption
              selected={value === AUTO_MODE_KEY}
              title={modeLabel(AUTO_MODE_KEY)}
              help={modeHelp(AUTO_MODE_KEY)}
              badge={<Badge tone="brand">推荐</Badge>}
              onClick={() => onChange(AUTO_MODE_KEY)}
            />
            {ALL_MODES.map((mode) => (
              <ModeOption
                key={mode}
                selected={mode === value}
                title={modeLabel(mode)}
                help={modeHelp(mode)}
                badge={
                  MODE_HAS_LEAD[mode] ? (
                    <Badge tone="team">有主导</Badge>
                  ) : mode === "solo" ? (
                    <Badge tone="muted">单 Agent</Badge>
                  ) : null
                }
                onClick={() => onChange(mode)}
              />
            ))}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Badge({
  children,
  tone,
}: {
  readonly children: string;
  readonly tone: "brand" | "team" | "muted";
}) {
  return (
    <span
      className={cn(
        "rounded-full border px-1.5 py-0.5 text-[10px] font-medium",
        tone === "brand" &&
          "border-[var(--brand)]/30 bg-[var(--brand-soft)] text-[var(--brand)]",
        tone === "team" &&
          "border-[var(--color-team)]/25 bg-[color-mix(in_srgb,var(--color-team)_10%,transparent)] text-[var(--color-team)]",
        tone === "muted" &&
          "border-[var(--border)] bg-[var(--fill-secondary)] text-[var(--text-muted)]",
      )}
    >
      {children}
    </span>
  );
}

function ModeOption({
  selected,
  title,
  help,
  badge,
  onClick,
}: {
  readonly selected: boolean;
  readonly title: string;
  readonly help: string;
  readonly badge?: ReactNode;
  readonly onClick: () => void;
}) {
  return (
    <Dialog.Close asChild>
      <button
        type="button"
        className={cn(
          "cursor-pointer rounded-[var(--radius-lg)] border p-3 text-left transition-all duration-150",
          "bg-[var(--surface)]",
          selected
            ? "border-[var(--accent)] shadow-[0_0_0_1px_var(--accent)]"
            : "border-[var(--border)] hover:border-[var(--text-faint)] hover:bg-[var(--fill-hover)]",
          focusRing,
        )}
        onClick={onClick}
      >
        <div className="flex flex-wrap items-center gap-2">
          <strong className="text-[13px] font-semibold text-[var(--text)]">{title}</strong>
          {badge}
        </div>
        <p className={cn("m-0 mt-1 text-[12px] leading-relaxed", mutedText)}>{help}</p>
      </button>
    </Dialog.Close>
  );
}
