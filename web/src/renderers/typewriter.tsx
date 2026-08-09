import { useEffect, useState } from "react";
import { splitSentences } from "../projectors/message-projector";

import { mutedText } from "../lib/ui";

export function TypewriterAnswer({ text, active }: { readonly text: string; readonly active: boolean }) {
  const [visible, setVisible] = useState(0);
  const sentences = splitSentences(text);

  useEffect(() => {
    setVisible(0);
    if (!active || sentences.length === 0) return;
    let i = 0;
    const timer = window.setInterval(() => {
      i += 1;
      setVisible(i);
      if (i >= sentences.length) window.clearInterval(timer);
    }, 420);
    return () => window.clearInterval(timer);
  }, [text, active, sentences.length]);

  if (!text) return <p className={mutedText}>等待团队收口…</p>;
  if (!active) return <p>{text}</p>;
  return (
    <p>
      {sentences.slice(0, visible).join(" ")}
      {visible < sentences.length ? <span className="text-run">▍</span> : null}
    </p>
  );
}
