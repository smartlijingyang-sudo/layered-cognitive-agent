import { ArrowRightLeft } from "lucide-react";
import type { Message } from "../../../projectors/message-types";
import { cn } from "../../../lib/cn";
import { LobeIcon } from "../../../lib/icons";
import { mutedText } from "../../../lib/ui";

export function DelegationMessage({ message }: { readonly message: Message }) {
  const meta = message.metadata;
  const running = message.status === "running";
  const calleeRole = meta?.calleeRole ?? "unknown";

  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5">
      <div className="flex items-center gap-2 text-sm font-medium text-[var(--text)]">
        <span
          className={cn(
            "text-[var(--text-muted)]",
            message.status === "error" && "text-[var(--color-danger)]",
          )}
        >
          <LobeIcon icon={ArrowRightLeft} size="sm" />
        </span>
        {running ? `⇢ 委派 → ${calleeRole}` : `⇠ ${calleeRole} 完成`}
      </div>
      {(running ? meta?.subtaskPreview : meta?.resultPreview || meta?.subtaskPreview) ? (
        <p className={cn("m-0 mt-1 text-sm whitespace-pre-wrap", mutedText)}>
          {running
            ? meta?.subtaskPreview || undefined
            : meta?.resultPreview || meta?.subtaskPreview || undefined}
        </p>
      ) : null}
    </div>
  );
}
