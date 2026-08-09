import { Paperclip } from "lucide-react";
import type { Turn } from "../../domain/conversation";
import { formatByteSize } from "../../lib/file-mime-icon";
import { modeLabel } from "../../lib/modes";
import { cn } from "../../lib/cn";
import { LobeIcon } from "../../lib/icons";

export function UserBubble({ turn }: { readonly turn: Turn }) {
  const attachments = turn.attachments ?? [];

  return (
    <div className="lobe-user-msg flex flex-col items-end gap-1.5">
      {attachments.length > 0 ? (
        <ul
          className="m-0 flex max-w-[min(100%,80%)] list-none flex-wrap justify-end gap-1.5 p-0"
          aria-label="已附加文件"
          data-testid="user-attachments"
        >
          {attachments.map((att) => (
            <li
              key={att.id}
              className={cn(
                "inline-flex max-w-full items-center gap-1.5 rounded-full",
                "border border-[var(--border)] bg-[var(--surface)]",
                "px-2.5 py-1 text-[11px] text-[var(--text-muted)]",
              )}
              data-testid="user-attachment-chip"
              title={att.error ?? att.name}
            >
              <LobeIcon icon={Paperclip} size="xs" className="shrink-0 text-[var(--text-faint)]" />
              <span className="max-w-[9rem] truncate text-[var(--text)]">{att.name}</span>
              {formatByteSize(att.sizeBytes) ? (
                <span className="text-[var(--text-faint)]">{formatByteSize(att.sizeBytes)}</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      <article
        className={cn(
          "max-w-[min(100%,80%)] rounded-[18px] rounded-br-[6px]",
          "bg-[var(--user-bubble)] px-4 py-2.5",
          "text-[0.9375rem] leading-[1.65] text-[var(--text)]",
        )}
      >
        <p className="m-0 whitespace-pre-wrap break-words">{turn.question}</p>
      </article>
      <span className="px-1.5 text-[11px] text-[var(--text-faint)]">{modeLabel(turn.mode)}</span>
    </div>
  );
}
