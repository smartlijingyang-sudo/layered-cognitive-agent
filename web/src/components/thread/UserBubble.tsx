import { Paperclip } from "lucide-react";
import type { Turn } from "../../domain/conversation";
import { formatByteSize } from "../../lib/file-mime-icon";
import { modeLabel } from "../../lib/modes";
import { cn } from "../../lib/cn";

export function UserBubble({ turn }: { readonly turn: Turn }) {
  const attachments = turn.attachments ?? [];

  return (
    <div className="flex flex-col items-end gap-1.5">
      {attachments.length > 0 ? (
        <ul
          className="m-0 flex max-w-[min(100%,85%)] list-none flex-wrap justify-end gap-1.5 p-0"
          aria-label="已附加文件"
          data-testid="user-attachments"
        >
          {attachments.map((att) => (
            <li
              key={att.id}
              className={cn(
                "inline-flex max-w-full items-center gap-1.5 rounded-full border border-border/60",
                "bg-surface px-2.5 py-1 text-[11px] text-text-muted",
              )}
              data-testid="user-attachment-chip"
              title={att.error ?? att.name}
            >
              <Paperclip size={11} className="shrink-0 text-accent" aria-hidden />
              <span className="max-w-[9rem] truncate text-text">{att.name}</span>
              {formatByteSize(att.sizeBytes) ? (
                <span className="text-[var(--text-faint)]">{formatByteSize(att.sizeBytes)}</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
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
