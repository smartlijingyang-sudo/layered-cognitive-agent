import { cn } from "../../lib/cn";
import { softBadge } from "../../lib/ui";

export function LlmBadge({ available }: { readonly available: boolean | null }) {
  if (available === null) {
    return (
      <span className={cn(softBadge, "text-[var(--text-faint)]")}>
        <span className="size-1.5 rounded-full bg-[var(--text-faint)]" aria-hidden />
        检测中
      </span>
    );
  }
  return (
    <span
      className={cn(
        softBadge,
        available ? "text-[var(--color-success)]" : "text-[var(--color-warning)]",
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          available ? "bg-[var(--color-success)]" : "bg-[var(--color-warning)]",
        )}
        aria-hidden
      />
      {available ? "LLM 在线" : "LLM 未配置"}
    </span>
  );
}
