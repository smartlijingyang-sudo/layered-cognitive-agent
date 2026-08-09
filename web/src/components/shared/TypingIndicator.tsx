import { cn } from "../../lib/cn";

export function TypingIndicator({ label }: { readonly label?: string }) {
  return (
    <div
      className="flex items-center gap-2.5 py-1.5 pl-0.5 text-[var(--text-muted)]"
      aria-live="polite"
    >
      <span className="inline-flex items-center gap-1" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="lobe-typing-dot inline-block size-1.5 rounded-full bg-[var(--text-faint)]"
            style={{ animationDelay: `${i * 160}ms` }}
          />
        ))}
      </span>
      <span className={cn("text-sm", "lobe-shiny")}>{label ?? "正在生成…"}</span>
    </div>
  );
}
