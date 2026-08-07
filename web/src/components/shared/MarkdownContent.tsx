import { useCallback, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Copy, Check } from "lucide-react";

function CodeBlock({ children, className }: { readonly children: ReactNode; readonly className?: string }) {
  const [copied, setCopied] = useState(false);
  const text = String(children).replace(/\n$/, "");
  const onCopy = useCallback(async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }, [text]);

  return (
    <div className="code-block">
      <button type="button" className="code-copy" onClick={() => void onCopy()} aria-label="复制代码">
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
    return <p className="muted">等待回答…</p>;
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
              <code className="inline-code" {...props}>
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
