import { cn } from "../../lib/cn";

export function LlmBadge({ available }: { readonly available: boolean | null }) {
  if (available === null) return null;
  return (
    <span
      className={cn(
        "rounded-full border border-border px-2 py-0.5 text-xs",
        available ? "text-run" : "text-resource",
      )}
    >
      {available ? "LLM 在线" : "LLM 未配置"}
    </span>
  );
}
