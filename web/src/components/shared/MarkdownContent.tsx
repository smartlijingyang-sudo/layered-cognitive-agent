import { useCallback, useMemo, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Copy, Check } from "lucide-react";
import { normalizeChatMarkdown } from "../../lib/normalize-chat-markdown";
import { sanitizeAssistantDisplayText } from "../../lib/extract-decision-text";
import { cn } from "../../lib/cn";
import { focusRing, mutedText } from "../../lib/ui";

function CodeBlock({ children, className }: { readonly children: ReactNode; readonly className?: string }) {
  const [copied, setCopied] = useState(false);
  const text = String(children).replace(/\n$/, "");
  const onCopy = useCallback(async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }, [text]);

  return (
    <div className="code-block relative my-3">
      <button
        type="button"
        className={cn(
          "absolute top-2 right-2 rounded-md border border-white/10 bg-white/10 p-1 text-inherit opacity-70 transition-opacity hover:opacity-100",
          focusRing,
        )}
        onClick={() => void onCopy()}
        aria-label="复制代码"
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </button>
      <pre className={className}>
        <code>{text}</code>
      </pre>
    </div>
  );
}

export function MarkdownContent({
  text,
  streaming = false,
}: {
  readonly text: string;
  readonly streaming?: boolean;
}) {
  const sanitized = useMemo(
    () => sanitizeAssistantDisplayText(text, streaming),
    [text, streaming],
  );
  const normalized = useMemo(
    () => normalizeChatMarkdown(sanitized, streaming ? "streaming" : "final"),
    [sanitized, streaming],
  );

  if (!normalized.trim()) {
    return <p className={cn("m-0", mutedText)}>等待回答…</p>;
  }

  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre: ({ children }) => <>{children}</>,
          p: ({ children }) => <p className="md-p">{children}</p>,
          ul: ({ children }) => <ul className="md-ul">{children}</ul>,
          ol: ({ children }) => <ol className="md-ol">{children}</ol>,
          li: ({ children }) => <li className="md-li">{children}</li>,
          h1: ({ children }) => <h1 className="md-h1">{children}</h1>,
          h2: ({ children }) => <h2 className="md-h2">{children}</h2>,
          h3: ({ children }) => <h3 className="md-h3">{children}</h3>,
          code: ({ className, children, ...props }) => {
            const isBlock = Boolean(className);
            if (isBlock) {
              return <CodeBlock className={className}>{children}</CodeBlock>;
            }
            return (
              <code
                className="rounded bg-[color-mix(in_srgb,var(--surface)_80%,var(--text)_5%)] px-1 py-0.5 font-mono text-[0.9em]"
                {...props}
              >
                {children}
              </code>
            );
          },
        }}
      >
        {normalized}
      </ReactMarkdown>
    </div>
  );
}
