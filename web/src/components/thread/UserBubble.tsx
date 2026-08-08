import type { Turn } from "../../domain/conversation";
import { modeLabel } from "../../lib/modes";
import { cn } from "../../lib/cn";

export function UserBubble({ turn }: { readonly turn: Turn }) {
  return (
    <div className="flex flex-col items-end gap-1.5">
      <article
        className={cn(
          "max-w-[min(100%,85%)] rounded-[var(--radius-xl)] rounded-br-[var(--radius-sm)]",
          "bg-[var(--user-bubble)] px-4 py-3",
          "text-[0.9375rem] leading-[1.65] text-text shadow-sm",
          "ring-1 ring-border/40",
        )}
      >
        <p className="m-0 whitespace-pre-wrap break-words">{turn.question}</p>
      </article>
      <span className="px-1 text-[11px] text-[var(--text-faint)]">{modeLabel(turn.mode)}</span>
    </div>
  );
}
