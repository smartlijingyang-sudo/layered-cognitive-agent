import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  BookOpen,
  Check,
  ChevronDown,
  Package,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import type { SandboxBlock, ToolBlock } from "../../projectors/types";
import { formatProcessDuration } from "../../lib/format-duration";
import { LobeIcon } from "../../lib/icons";
import { MarkdownContent } from "../shared/MarkdownContent";
import { cn } from "../../lib/cn";
import { focusRing } from "../../lib/ui";
import { AnsiOutput } from "./AnsiOutput";
import { CodeHighlight } from "./CodeHighlight";
import { SandboxPanel } from "./SandboxPanel";
import { StatusBlock } from "./StatusBlock";
import {
  extractCode,
  extractCommand,
  extractSkillId,
  getToolApiLabel,
  getToolDisplayName,
  getToolFirstDetail,
  getToolHumanSummary,
  isCodeLikeTool,
  isCommandLikeTool,
  isSkillLikeTool,
  parseToolArgs,
} from "./tool-display";
import { WORKFLOW_EASE_CSS } from "./workflow-constants";

function formatLatency(ms?: number): string | null {
  if (ms == null || ms <= 0) return null;
  if (ms >= 1000) {
    const d = formatProcessDuration(ms);
    return d ?? `${(ms / 1000).toFixed(1)}s`;
  }
  return `${ms}ms`;
}

function Chip({
  icon,
  children,
  className,
}: {
  readonly icon?: ReactNode;
  readonly children: ReactNode;
  readonly className?: string;
}) {
  return (
    <span className={cn("lobe-tool-chip", className)}>
      {icon}
      <span className="lobe-tool-chip-text">{children}</span>
    </span>
  );
}

function ToolInspectorTitle({
  block,
  running,
}: {
  readonly block: ToolBlock;
  readonly running: boolean;
}) {
  const args = useMemo(() => parseToolArgs(block.argumentsPreview), [block.argumentsPreview]);
  const apiLabel = getToolApiLabel(block.toolName);
  const displayLabel = getToolDisplayName(block.toolName);
  const human = getToolHumanSummary(args);
  const detail = human || getToolFirstDetail(block);

  if (isCommandLikeTool(block.toolName) || isCodeLikeTool(block.toolName)) {
    return (
      <div
        className={cn(
          "lobe-inspector-title flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden text-sm",
          running && "lobe-shiny",
        )}
      >
        <span className="shrink-0 text-[var(--text-muted)]">{displayLabel}</span>
        {detail ? (
          <>
            <span className="shrink-0 text-[var(--text-faint)]">·</span>
            <span className="min-w-0 truncate text-[var(--text)]">{detail}</span>
          </>
        ) : null}
        {!running && block.status === "done" && block.ok !== false ? (
          <LobeIcon icon={Check} size="sm" className="shrink-0 text-[var(--color-success)]" />
        ) : null}
        {!running && (block.status === "error" || block.ok === false) ? (
          <LobeIcon icon={X} size="sm" className="shrink-0 text-[var(--color-danger)]" />
        ) : null}
      </div>
    );
  }

  if (isSkillLikeTool(block.toolName)) {
    const skill = extractSkillId(args) || detail;
    const icon =
      block.toolName === "search_skill" ? (
        <LobeIcon icon={Search} size="xs" className="text-[var(--text-faint)]" />
      ) : block.toolName === "import_skill" ? (
        <LobeIcon icon={Package} size="xs" className="text-[var(--text-faint)]" />
      ) : block.toolName === "read_skill_reference" ? (
        <LobeIcon icon={BookOpen} size="xs" className="text-[var(--text-faint)]" />
      ) : (
        <LobeIcon icon={Sparkles} size="xs" className="text-[var(--color-thinking)]" />
      );
    return (
      <div
        className={cn(
          "lobe-inspector-title flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden",
          running && "lobe-shiny",
        )}
      >
        <span className="shrink-0 text-sm text-[var(--text-muted)]">{displayLabel}</span>
        {skill ? (
          <Chip icon={icon} className="lobe-tool-chip--bordered">
            {skill}
          </Chip>
        ) : null}
      </div>
    );
  }

  // Generic: Plugin › api (param)
  return (
    <div
      className={cn(
        "lobe-inspector-title min-w-0 flex-1 overflow-hidden text-sm",
        "line-clamp-1 text-[var(--text-muted)]",
        running && "lobe-shiny",
      )}
    >
      <span>{apiLabel}</span>
      {detail ? (
        <>
          <span className="font-mono text-[var(--text-faint)]"> (</span>
          <span className="font-mono text-xs text-[var(--text-muted)]">{detail}</span>
          <span className="font-mono text-[var(--text-faint)]">)</span>
        </>
      ) : null}
      {block.agentRole ? (
        <span className="text-[var(--text-faint)]"> · {block.agentRole}</span>
      ) : null}
    </div>
  );
}

function ToolExpandBody({
  block,
  sandbox,
}: {
  readonly block: ToolBlock;
  readonly sandbox?: SandboxBlock;
}) {
  const args = useMemo(() => parseToolArgs(block.argumentsPreview), [block.argumentsPreview]);

  if (isCommandLikeTool(block.toolName)) {
    const command = extractCommand(args);
    const output =
      sandbox?.stdout ||
      (block.resultPreview?.trim() && !block.resultPreview.trim().startsWith("{")
        ? block.resultPreview
        : "");
    const stderr = sandbox?.stderr || "";
    return (
      <div className="lobe-tool-detail grid gap-2">
        {command ? (
          <section>
            <h4 className="lobe-tool-section-label">命令</h4>
            <CodeHighlight code={command} language="sh" />
          </section>
        ) : null}
        {output ? (
          <section>
            <h4 className="lobe-tool-section-label">输出</h4>
            <AnsiOutput text={output} />
          </section>
        ) : null}
        {stderr.trim() ? (
          <section>
            <h4 className="lobe-tool-section-label">错误</h4>
            <AnsiOutput text={stderr} tone="error" />
          </section>
        ) : null}
        {sandbox && !sandbox.sealed && !output ? (
          <SandboxPanel block={sandbox} compact />
        ) : null}
      </div>
    );
  }

  if (isSkillLikeTool(block.toolName)) {
    const skill = extractSkillId(args);
    const body = block.resultPreview?.trim() || "";
    const skillText = extractSkillMarkdown(body);
    return (
      <div className="lobe-skill-card overflow-hidden rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)]">
        <div className="border-b border-[var(--border-subtle)] bg-[var(--fill-secondary)] px-3 py-2">
          <div className="text-[13px] font-semibold text-[var(--text)]">
            {skill || getToolApiLabel(block.toolName)}
          </div>
          <div className="mt-0.5 text-[11px] text-[var(--text-muted)]">
            {block.toolName === "activate_skill"
              ? "技能指南"
              : block.toolName === "search_skill"
                ? "搜索结果"
                : "技能内容"}
          </div>
        </div>
        {skillText ? (
          <div className="lobe-skill-body max-h-[min(40vh,400px)] overflow-y-auto px-4 py-3">
            {skillText.startsWith("{") || skillText.startsWith("[") ? (
              <CodeHighlight code={tryPrettyJson(skillText)} language="json" maxHeightClass="max-h-[360px]" />
            ) : (
              <div className="thinking-content">
                <MarkdownContent text={skillText} />
              </div>
            )}
          </div>
        ) : null}
      </div>
    );
  }

  if (isCodeLikeTool(block.toolName)) {
    const code = extractCode(args);
    const lang = block.toolName === "calculator" ? "text" : "python";
    const output =
      sandbox?.stdout ||
      (block.resultPreview?.trim() && !block.resultPreview.trim().startsWith("{")
        ? block.resultPreview
        : "");
    return (
      <div className="lobe-tool-detail grid gap-2">
        {code ? (
          <section>
            <h4 className="lobe-tool-section-label">
              {block.toolName === "sandbox_execute" ? "代码" : "输入"}
            </h4>
            <CodeHighlight code={code} language={lang} />
          </section>
        ) : null}
        {sandbox && !sandbox.sealed ? <SandboxPanel block={sandbox} compact /> : null}
        {output ? (
          <section>
            <h4 className="lobe-tool-section-label">输出</h4>
            <AnsiOutput text={output} />
          </section>
        ) : null}
        {sandbox?.stderr?.trim() ? (
          <section>
            <h4 className="lobe-tool-section-label">错误</h4>
            <AnsiOutput text={sandbox.stderr} tone="error" />
          </section>
        ) : null}
        {!output && block.resultPreview?.trim() ? (
          <section>
            <h4 className="lobe-tool-section-label">结果</h4>
            <AnsiOutput text={tryPrettyJson(block.resultPreview)} />
          </section>
        ) : null}
      </div>
    );
  }

  // Generic args + result
  return (
    <div className="grid gap-2">
      {block.argumentsPreview?.trim() ? (
        <section>
          <h4 className="m-0 mb-1 text-[11px] font-medium uppercase tracking-wide text-[var(--text-faint)]">
            参数
          </h4>
          <CodeHighlight
            code={tryPrettyJson(block.argumentsPreview)}
            language="json"
            maxHeightClass="max-h-40"
          />
        </section>
      ) : null}
      {sandbox ? <SandboxPanel block={sandbox} compact /> : null}
      {block.error?.trim() ? (
        <p className="m-0 text-sm text-[var(--color-danger)]">{block.error}</p>
      ) : null}
      {block.resultPreview?.trim() ? (
        <section>
          <h4 className="m-0 mb-1 text-[11px] font-medium uppercase tracking-wide text-[var(--text-faint)]">
            结果
          </h4>
          <CodeHighlight
            code={tryPrettyJson(block.resultPreview)}
            language="json"
            maxHeightClass="max-h-48"
          />
        </section>
      ) : null}
    </div>
  );
}

function tryPrettyJson(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

/** Pull markdown from activate_skill JSON payload `{ text: "..." }`. */
function extractSkillMarkdown(raw: string): string {
  if (!raw.trim()) return "";
  try {
    const parsed = JSON.parse(raw) as { text?: string };
    if (typeof parsed.text === "string" && parsed.text.trim()) {
      return parsed.text;
    }
  } catch {
    // plain markdown / text
  }
  return raw;
}

/**
 * LobeHub tool accordion: status block + specialized inspector + expand body.
 */
export function ToolCallCard({
  block,
  sandbox,
  defaultOpen,
}: {
  readonly block: ToolBlock;
  readonly sandbox?: SandboxBlock;
  readonly defaultOpen?: boolean;
}) {
  const running = block.status === "running" || block.status === "pending";
  const hasBody =
    Boolean(block.argumentsPreview?.trim()) ||
    Boolean(block.resultPreview?.trim()) ||
    Boolean(block.error?.trim()) ||
    Boolean(sandbox);

  const [open, setOpen] = useState(
    defaultOpen ?? (running || Boolean(sandbox && !sandbox.sealed)),
  );

  useEffect(() => {
    if (running || (sandbox && !sandbox.sealed)) setOpen(true);
  }, [running, sandbox]);

  const latency = formatLatency(block.latencyMs);
  const statusVariant =
    running
      ? "neural"
      : block.status === "error" || block.ok === false
        ? "error"
        : "success";

  return (
    <div className="lobe-tool-row min-w-0">
      <button
        type="button"
        className={cn(
          "lobe-accordion-trigger flex w-full cursor-pointer items-center gap-1.5",
          "border-0 bg-transparent py-1 text-left",
          focusRing,
        )}
        onClick={() => hasBody && setOpen((v) => !v)}
        aria-expanded={open}
        disabled={!hasBody}
      >
        <StatusBlock variant={statusVariant} />
        <ToolInspectorTitle block={block} running={running} />
        {latency ? (
          <span className="shrink-0 text-xs text-[var(--text-faint)]">{latency}</span>
        ) : null}
        {hasBody ? (
          <LobeIcon
            icon={ChevronDown}
            size="sm"
            className={cn(
              "shrink-0 text-[var(--text-faint)] transition-transform",
              open ? "rotate-180" : "",
            )}
            style={{ transitionDuration: "180ms", transitionTimingFunction: WORKFLOW_EASE_CSS }}
          />
        ) : null}
      </button>

      <div
        className={cn(
          "grid transition-[grid-template-rows,opacity]",
          open && hasBody ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
        )}
        style={{
          transitionDuration: "200ms",
          transitionTimingFunction: WORKFLOW_EASE_CSS,
        }}
      >
        <div className="min-h-0 overflow-hidden">
          <div className="border-t border-dashed border-[var(--border-subtle)] py-2 pl-1">
            <ToolExpandBody block={block} sandbox={sandbox} />
          </div>
        </div>
      </div>
    </div>
  );
}
