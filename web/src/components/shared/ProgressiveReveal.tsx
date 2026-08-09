import { useEffect, useMemo, useState } from "react";
import { revealChunks } from "../../projectors/message-projector";

/** 渐进展示文本：真实 delta 序列即时全显，无 delta 时按句假流式。 */
export function useProgressiveReveal(
  text: string,
  deltas: readonly string[] | undefined,
  active: boolean,
): string {
  const deltaList = deltas ?? [];
  const chunks = useMemo(() => revealChunks(text, deltaList), [text, deltaList]);
  const hasRealDeltas = deltaList.length > 0;
  const [visibleCount, setVisibleCount] = useState(active && !hasRealDeltas ? 0 : chunks.length);

  useEffect(() => {
    if (!active || hasRealDeltas) {
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
  }, [active, chunks, hasRealDeltas]);

  return chunks.slice(0, visibleCount).join("") || text;
}

export function ProgressiveReveal({
  text,
  deltas,
  active,
}: {
  readonly text: string;
  readonly deltas?: readonly string[];
  readonly active: boolean;
}) {
  const visible = useProgressiveReveal(text, deltas, active);
  return <span>{visible}</span>;
}
