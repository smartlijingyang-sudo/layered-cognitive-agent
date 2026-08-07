import { cn } from "../../lib/cn";
import { mutedText } from "../../lib/ui";

export function TypingIndicator({ label }: { readonly label?: string }) {
  return (
    <div className={cn("flex items-center gap-2 py-1", mutedText)} aria-live="polite">
      <span className="inline-flex gap-1" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="inline-block size-1.5 rounded-full bg-accent animate-pulse"
            style={{ animationDelay: `${i * 180}ms` }}
          />
        ))}
      </span>
      <span className="text-sm">{label ?? "正在生成…"}</span>
    </div>
  );
}
