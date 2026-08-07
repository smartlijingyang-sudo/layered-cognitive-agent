import type { Turn } from "../../domain/conversation";
import { modeLabel } from "../../lib/modes";
import { cn } from "../../lib/cn";
import { elevatedSurface, mutedText } from "../../lib/ui";

export function UserBubble({ turn }: { readonly turn: Turn }) {
  return (
    <article className={cn(elevatedSurface, "border-l-[3px] border-l-cognitive px-4 py-3.5")}>
      <header className={cn("mb-1.5 text-xs", mutedText)}>你 · {modeLabel(turn.mode)}</header>
      <p className="m-0">{turn.question}</p>
    </article>
  );
}
