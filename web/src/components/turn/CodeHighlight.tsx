import { useEffect, useState } from "react";
import { highlightCode } from "../../lib/highlight-code";
import { cn } from "../../lib/cn";

/**
 * Shiki-backed code block for tool expands (shell / python / json).
 * Falls back to plain pre when highlighter fails.
 */
export function CodeHighlight({
  code,
  language = "sh",
  maxHeightClass = "max-h-[200px]",
  className,
}: {
  readonly code: string;
  readonly language?: string;
  readonly maxHeightClass?: string;
  readonly className?: string;
}) {
  const [html, setHtml] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void highlightCode(code, language).then((result) => {
      if (!cancelled) setHtml(result);
    });
    return () => {
      cancelled = true;
    };
  }, [code, language]);

  if (html) {
    return (
      <div
        className={cn(
          "lobe-code-highlight overflow-auto rounded-[var(--radius-sm)]",
          maxHeightClass,
          className,
        )}
        // HTML from our own Shiki path
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  }

  return (
    <pre
      className={cn(
        "m-0 overflow-auto rounded-[var(--radius-sm)] bg-[var(--fill-secondary)] p-2",
        "font-mono text-xs leading-relaxed text-[var(--text)] whitespace-pre-wrap break-all",
        maxHeightClass,
        className,
      )}
    >
      {code}
    </pre>
  );
}
