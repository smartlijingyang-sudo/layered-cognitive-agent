import type { Message } from "../../../projectors/message-types";
import { cn } from "../../../lib/cn";
import { mutedText } from "../../../lib/ui";

export function ErrorMessage({ message }: { readonly message: Message }) {
  const meta = message.metadata;

  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5">
      <div className="flex items-center gap-2 text-sm font-medium text-[var(--text)]">
        <span className="text-[var(--color-danger)]">✗</span>
        错误
      </div>
      <p className={cn("m-0 mt-1 text-sm whitespace-pre-wrap", mutedText)}>
        {meta?.errorMessage || message.content}
      </p>
    </div>
  );
}
