import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { Copy, Check } from "lucide-react";
import "katex/dist/katex.min.css";
import { normalizeChatMarkdown } from "../../lib/normalize-chat-markdown";
import { sanitizeAssistantDisplayText } from "../../lib/extract-decision-text";
import { isMermaidLanguage, parseCodeLanguage } from "../../lib/code-language";
import { highlightCode } from "../../lib/highlight-code";
import { useMermaidRender } from "../../lib/use-mermaid-render";
import { cn } from "../../lib/cn";
import { focusRing, mutedText } from "../../lib/ui";

function CopyButton({ text }: { readonly text: string }) {
  const [copied, setCopied] = useState(false);
  const onCopy = useCallback(async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }, [text]);

  return (
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
  );
}

function PlainCodeBlock({
  text,
  className,
}: {
  readonly text: string;
  readonly className?: string;
}) {
  return (
    <div className="code-block relative my-3">
      <CopyButton text={text} />
      <pre className={className}>
        <code>{text}</code>
      </pre>
    </div>
  );
}

function MermaidBlock({ source }: { readonly source: string }) {
  const state = useMermaidRender(source, true);

  if (state.status === "ready") {
    return (
      <div
        className="mermaid-block my-3 overflow-x-auto rounded-[var(--radius-md)] border border-border bg-surface p-3"
        // SVG from mermaid is trusted only after our own render path
        dangerouslySetInnerHTML={{ __html: state.svg }}
        data-testid="mermaid-diagram"
      />
    );
  }

  if (state.status === "error") {
    return (
      <div className="my-3" data-testid="mermaid-fallback">
        <p className={cn("m-0 mb-1 text-xs", mutedText)}>图表语法无效，已回退为源码</p>
        <PlainCodeBlock text={state.source} className="language-mermaid" />
      </div>
    );
  }

  // loading / idle — show source so content never disappears
  return (
    <div className="my-3" data-testid="mermaid-loading">
      <PlainCodeBlock text={source} className="language-mermaid" />
    </div>
  );
}

function HighlightedCodeBlock({
  text,
  language,
  className,
}: {
  readonly text: string;
  readonly language: string | undefined;
  readonly className?: string;
}) {
  const [html, setHtml] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setHtml(null);
    setFailed(false);
    void highlightCode(text, language).then((result) => {
      if (cancelled) return;
      if (result) {
        setHtml(result);
      } else {
        setFailed(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [text, language]);

  if (html && !failed) {
    return (
      <div className="code-block relative my-3" data-testid="highlighted-code">
        <CopyButton text={text} />
        <div
          className="shiki-wrap overflow-x-auto rounded-[var(--radius-md)] [&_pre]:m-0 [&_pre]:rounded-[var(--radius-md)] [&_pre]:p-3.5 [&_pre]:text-[0.8125rem] [&_pre]:leading-relaxed"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </div>
    );
  }

  // skeleton while loading, or plain fallback on failure — code never vanishes
  return <PlainCodeBlock text={text} className={className} />;
}

function FencedCode({
  className,
  children,
}: {
  readonly className?: string;
  readonly children: ReactNode;
}) {
  const language = parseCodeLanguage(className);
  const text = String(children).replace(/\n$/, "");

  if (isMermaidLanguage(language)) {
    return <MermaidBlock source={text} />;
  }

  return <HighlightedCodeBlock text={text} language={language} className={className} />;
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
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
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
              return <FencedCode className={className}>{children}</FencedCode>;
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
