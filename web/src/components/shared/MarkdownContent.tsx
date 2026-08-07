import { useCallback, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Copy, Check } from "lucide-react";
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
    <div className="code-block relative">
      <button
        type="button"
        className={cn(
          "absolute top-2 right-2 rounded-md border border-white/10 bg-white/10 p-1 text-inherit",
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

export function MarkdownContent({ text }: { readonly text: string }) {
  if (!text.trim()) {
    return <p className={mutedText}>等待回答…</p>;
  }
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre: ({ children }) => <>{children}</>,
          code: ({ className, children, ...props }) => {
            const isBlock = Boolean(className);
            if (isBlock) {
              return <CodeBlock className={className}>{children}</CodeBlock>;
            }
            return (
              <code
                className="rounded bg-[color-mix(in_srgb,var(--surface)_80%,var(--text)_5%)] px-1 py-0.5 font-mono text-[0.92em]"
                {...props}
              >
                {children}
              </code>
            );
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
