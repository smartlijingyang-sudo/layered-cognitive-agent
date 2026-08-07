import { useEffect, useMemo, useState } from "react";
import { revealChunks } from "../../projectors/chat-projector";

export function ProgressiveReveal({
  text,
  deltas,
  active,
}: {
  readonly text: string;
  readonly deltas?: readonly string[];
  readonly active: boolean;
}) {
  const chunks = useMemo(() => revealChunks(text, deltas ?? []), [text, deltas]);
  const [visibleCount, setVisibleCount] = useState(active ? 0 : chunks.length);

  useEffect(() => {
    if (!active) {
      setVisibleCount(chunks.length);
      return;
    }
    setVisibleCount(0);
    if (chunks.length === 0) return;
    let index = 0;
    const timer = window.setInterval(() => {
      index += 1;
      setVisibleCount(index);
      if (index >= chunks.length) {
        window.clearInterval(timer);
      }
    }, 420);
    return () => window.clearInterval(timer);
  }, [active, chunks]);

  const visible = chunks.slice(0, visibleCount).join("");
  return <span>{visible || text}</span>;
}
