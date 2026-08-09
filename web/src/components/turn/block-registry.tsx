import type { ReactElement } from "react";
import {
  ArrowRightLeft,
  Lightbulb,
  Sparkles,
  Users,
} from "lucide-react";
import type {
  CastingBlock,
  DecisionProcessBlock,
  DelegationBlock,
  InsightBlock,
  SandboxBlock,
  ThinkingBlock,
  ToolBlock,
  TurnProcessBlock,
} from "../../projectors/types";
import { cn } from "../../lib/cn";
import { mutedText } from "../../lib/ui";
import { ThinkingPanel } from "./ThinkingPanel";
import { ToolCallCard } from "./ToolCallCard";
import { SandboxPanel } from "./SandboxPanel";

function SimpleCard({
  icon,
  title,
  body,
  tone = "default",
}: {
  readonly icon: ReactElement;
  readonly title: string;
  readonly body?: string;
  readonly tone?: "default" | "error" | "success";
}) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5",
      )}
    >
      <div className="flex items-center gap-2 text-sm font-medium text-[var(--text)]">
        <span
          className={cn(
            "text-[var(--text-muted)]",
            tone === "error" && "text-[var(--color-danger)]",
            tone === "success" && "text-[var(--color-success)]",
          )}
        >
          {icon}
        </span>
        {title}
      </div>
      {body ? (
        <p className={cn("m-0 mt-1 text-sm whitespace-pre-wrap", mutedText)}>{body}</p>
      ) : null}
    </div>
  );
}

function CastingCard({ block }: { readonly block: CastingBlock }) {
  if (block.status === "running") {
    return (
      <SimpleCard
        icon={<Users size={14} />}
        title="◎ 智能选角"
        body={block.objectivePreview || "正在分析问题并挑选角色…"}
      />
    );
  }
  if (block.status === "error") {
    return (
      <SimpleCard
        icon={<Users size={14} />}
        title="✗ 组队失败"
        body={block.error}
        tone="error"
      />
    );
  }
  const roles = block.selectedRoles?.join("、") ?? "";
  const body = [
    block.governanceKind ? `协作方式：${block.governanceKind}` : null,
    block.leadRole ? `主导：${block.leadRole}` : null,
    roles ? `成员：${roles}` : null,
    block.rationale || null,
  ]
    .filter(Boolean)
    .join("\n");
  return <SimpleCard icon={<Users size={14} />} title="✓ 组队完成" body={body} tone="success" />;
}

function DecisionCard({ block }: { readonly block: DecisionProcessBlock }) {
  const target = block.delegateTarget ? ` → ${block.delegateTarget}` : "";
  const tool = block.toolName ? ` · ${block.toolName}` : "";
  const conf =
    block.confidence != null ? ` · 置信 ${(block.confidence * 100).toFixed(0)}%` : "";
  return (
    <SimpleCard
      icon={<Sparkles size={14} />}
      title={`决策 · step ${block.step}${block.agentRole ? ` · ${block.agentRole}` : ""}`}
      body={`${block.actionType}${target}${tool}${conf}${
        block.rationalePreview ? `\n${block.rationalePreview}` : ""
      }`}
    />
  );
}

function DelegationCard({ block }: { readonly block: DelegationBlock }) {
  const running = block.status === "running";
  return (
    <SimpleCard
      icon={<ArrowRightLeft size={14} />}
      title={running ? `⇢ 委派 → ${block.calleeRole}` : `⇠ ${block.calleeRole} 完成`}
      body={
        running
          ? block.subtaskPreview || undefined
          : block.resultPreview || block.subtaskPreview || undefined
      }
      tone={block.status === "error" ? "error" : "default"}
    />
  );
}

function InsightCard({ block }: { readonly block: InsightBlock }) {
  return (
    <SimpleCard
      icon={<Lightbulb size={14} />}
      title={block.summary || block.insightKind}
      body={block.detail || undefined}
    />
  );
}

export interface BlockRenderContext {
  /** Sandbox streams keyed by invocationId for nesting under tools. */
  readonly sandboxesByInvocation: ReadonlyMap<string, SandboxBlock>;
  /** Invocation ids already rendered under a tool card. */
  readonly nestedSandboxIds: ReadonlySet<string>;
}

/**
 * Render a process block. Sandbox blocks nested under a matching tool are skipped
 * when rendered via the tool card (see ProcessBlocks).
 */
export function renderProcessBlock(
  block: TurnProcessBlock,
  ctx: BlockRenderContext,
): ReactElement | null {
  switch (block.kind) {
    case "casting":
      return <CastingCard key={block.id} block={block} />;
    case "thinking":
      return <ThinkingPanel key={block.id} block={block as ThinkingBlock} />;
    case "tool": {
      const tool = block as ToolBlock;
      const sandbox = tool.invocationId
        ? ctx.sandboxesByInvocation.get(tool.invocationId)
        : undefined;
      return <ToolCallCard key={block.id} block={tool} sandbox={sandbox} />;
    }
    case "sandbox": {
      if (ctx.nestedSandboxIds.has(block.invocationId)) return null;
      return <SandboxPanel key={block.id} block={block as SandboxBlock} />;
    }
    case "delegation":
      return <DelegationCard key={block.id} block={block as DelegationBlock} />;
    case "decision":
      return <DecisionCard key={block.id} block={block as DecisionProcessBlock} />;
    case "insight":
      return <InsightCard key={block.id} block={block as InsightBlock} />;
    default:
      return null;
  }
}

/** Render ordered process blocks with tool↔sandbox nesting. */
export function ProcessBlocks({ blocks }: { readonly blocks: readonly TurnProcessBlock[] }) {
  const sandboxesByInvocation = new Map<string, SandboxBlock>();
  for (const b of blocks) {
    if (b.kind === "sandbox" && b.invocationId) {
      sandboxesByInvocation.set(b.invocationId, b);
    }
  }
  const nestedSandboxIds = new Set<string>();
  for (const b of blocks) {
    if (b.kind === "tool" && b.invocationId && sandboxesByInvocation.has(b.invocationId)) {
      nestedSandboxIds.add(b.invocationId);
    }
  }
  const ctx: BlockRenderContext = { sandboxesByInvocation, nestedSandboxIds };
  return (
    <div className="grid gap-2.5">
      {blocks.map((block) => renderProcessBlock(block, ctx))}
    </div>
  );
}
