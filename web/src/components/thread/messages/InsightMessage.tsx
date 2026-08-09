import { Lightbulb } from "lucide-react";
import type { Message } from "../../../projectors/message-types";
import { cn } from "../../../lib/cn";
import { LobeIcon } from "../../../lib/icons";
import { mutedText } from "../../../lib/ui";

export function InsightMessage({ message }: { readonly message: Message }) {
  const meta = message.metadata;

  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5">
      <div className="flex items-center gap-2 text-sm font-medium text-[var(--text)]">
        <span className="text-[var(--text-muted)]">
          <LobeIcon icon={Lightbulb} size="sm" />
        </span>
        {meta?.summary || meta?.insightKind || "洞察"}
      </div>
      {meta?.detail ? (
        <p className={cn("m-0 mt-1 text-sm whitespace-pre-wrap", mutedText)}>{meta.detail}</p>
      ) : null}
    </div>
  );
}
