import { useEffect, useMemo, useState } from "react";
import { splitSentences } from "../../projectors/chat-projector";

export function ProgressiveReveal({
  text,
  active,
}: {
  readonly text: string;
  readonly active: boolean;
}) {
  const sentences = useMemo(() => splitSentences(text), [text]);
  const [visibleCount, setVisibleCount] = useState(active ? 0 : sentences.length);

  useEffect(() => {
    if (!active) {
      setVisibleCount(sentences.length);
      return;
    }
    setVisibleCount(0);
    if (sentences.length === 0) return;
    let index = 0;
    const timer = window.setInterval(() => {
      index += 1;
      setVisibleCount(index);
      if (index >= sentences.length) {
        window.clearInterval(timer);
      }
    }, 420);
    return () => window.clearInterval(timer);
  }, [active, sentences]);

  const visible = sentences.slice(0, visibleCount).join(" ");
  return <span>{visible || text}</span>;
}
