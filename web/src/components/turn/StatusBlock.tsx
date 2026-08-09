import type { ReactNode } from "react";
import {
  AlertTriangle,
  Atom,
  Ban,
  Check,
  Hand,
  Loader2,
  Pause,
  X,
} from "lucide-react";
import { cn } from "../../lib/cn";
import {
  ICON_STROKE,
  ICON_STROKE_BOLD,
  STATUS_BLOCK_PX,
  STATUS_ICON_PX,
} from "../../lib/icons";
import { NeuralNetworkLoading } from "../shared/NeuralNetworkLoading";

export type StatusBlockVariant =
  | "loading"
  | "neural"
  | "success"
  | "error"
  | "partial"
  | "pending"
  | "aborted"
  | "rejected"
  | "thinking"
  | "thinking-done"
  | "thinking-done-active";

/**
 * LobeHub 24×24 outlined status chip (Thinking / Workflow / Tool rows).
 * Icons: 14px glyph + stroke 2; neural loader 16px SVG.
 */
export function StatusBlock({
  variant,
  className,
}: {
  readonly variant: StatusBlockVariant;
  readonly className?: string;
}) {
  let icon: ReactNode;
  let colorClass = "text-[var(--text-muted)]";

  switch (variant) {
    case "loading":
      icon = (
        <Loader2 size={STATUS_ICON_PX} strokeWidth={ICON_STROKE} className="animate-spin" />
      );
      break;
    case "neural":
      icon = <NeuralNetworkLoading />;
      break;
    case "success":
      icon = <Check size={STATUS_ICON_PX} strokeWidth={ICON_STROKE_BOLD} />;
      colorClass = "text-[var(--color-success)]";
      break;
    case "error":
      icon = <X size={STATUS_ICON_PX} strokeWidth={ICON_STROKE_BOLD} />;
      colorClass = "text-[var(--color-danger)]";
      break;
    case "partial":
      icon = (
        <span className="relative inline-flex">
          <Check
            size={STATUS_ICON_PX}
            strokeWidth={ICON_STROKE_BOLD}
            className="text-[var(--color-success)]"
          />
          <span className="absolute -right-0.5 -bottom-0.5 flex size-2.5 items-center justify-center rounded-full bg-[var(--surface)]">
            <AlertTriangle size={8} strokeWidth={ICON_STROKE} className="text-[var(--color-warning)]" />
          </span>
        </span>
      );
      colorClass = "";
      break;
    case "pending":
      icon = <Hand size={STATUS_ICON_PX} strokeWidth={ICON_STROKE} />;
      colorClass = "text-[var(--color-info)]";
      break;
    case "aborted":
      icon = <Pause size={STATUS_ICON_PX} strokeWidth={ICON_STROKE} />;
      colorClass = "text-[var(--text-faint)]";
      break;
    case "rejected":
      icon = <Ban size={STATUS_ICON_PX} strokeWidth={ICON_STROKE} />;
      colorClass = "text-[var(--text-faint)]";
      break;
    case "thinking":
      icon = (
        <Loader2 size={STATUS_ICON_PX} strokeWidth={ICON_STROKE} className="animate-spin" />
      );
      colorClass = "text-[var(--text-muted)]";
      break;
    case "thinking-done-active":
      icon = <Atom size={STATUS_ICON_PX} strokeWidth={ICON_STROKE} />;
      colorClass = "text-[var(--color-thinking)]";
      break;
    case "thinking-done":
    default:
      icon = <Atom size={STATUS_ICON_PX} strokeWidth={ICON_STROKE} />;
      colorClass = "text-[var(--text-muted)]";
      break;
  }

  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-[var(--radius-sm)]",
        "border bg-transparent",
        variant === "thinking-done-active"
          ? "border-[color-mix(in_srgb,var(--color-thinking)_45%,var(--border))]"
          : "border-[var(--border)]",
        colorClass,
        className,
      )}
      style={{
        width: STATUS_BLOCK_PX,
        height: STATUS_BLOCK_PX,
        fontSize: STATUS_ICON_PX,
      }}
      aria-hidden
    >
      {icon}
    </span>
  );
}
