import type { ReactElement } from "react";
import {
  ArrowRightLeft,
  Lightbulb,
  Sparkles,
  Users,
} from "lucide-react";
import type {
  ActivityBlock,
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
import { LobeIcon } from "../../lib/icons";
import { mutedText } from "../../lib/ui";
import { ThinkingPanel } from "./ThinkingPanel";
import { ToolCallCard } from "./ToolCallCard";
import { SandboxPanel } from "./SandboxPanel";
import { WorkflowCollapse } from "./WorkflowCollapse";
import { StatusBlock } from "./StatusBlock";
import { WORKFLOW_MULTI_TOOL_THRESHOLD } from "./workflow-constants";

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
        icon={<LobeIcon icon={Users} size="sm" />}
        title="◎ 智能选角"
        body={block.objectivePreview || "正在分析问题并挑选角色…"}
      />
    );
  }
  if (block.status === "error") {
    return (
      <SimpleCard
        icon={<LobeIcon icon={Users} size="sm" />}
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
  return (
    <SimpleCard
      icon={<LobeIcon icon={Users} size="sm" />}
      title="✓ 组队完成"
      body={body}
      tone="success"
    />
  );
}

function DecisionCard({ block }: { readonly block: DecisionProcessBlock }) {
  const target = block.delegateTarget ? ` → ${block.delegateTarget}` : "";
  const tool = block.toolName ? ` · ${block.toolName}` : "";
  const conf =
    block.confidence != null ? ` · 置信 ${(block.confidence * 100).toFixed(0)}%` : "";
  return (
    <SimpleCard
      icon={<LobeIcon icon={Sparkles} size="sm" />}
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
      icon={<LobeIcon icon={ArrowRightLeft} size="sm" />}
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
      icon={<LobeIcon icon={Lightbulb} size="sm" />}
      title={block.summary || block.insightKind}
      body={block.detail || undefined}
    />
  );
}

function ActivityCard({ block }: { readonly block: ActivityBlock }) {
  const variant = block.status === "running" ? "neural" : "thinking-done";
  return (
    <div className="flex items-center gap-2 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2">
      <StatusBlock variant={variant} />
      <span className="text-sm text-[var(--text-muted)]">{block.detail}</span>
    </div>
  );
}

export interface BlockRenderContext {
  readonly sandboxesByInvocation: ReadonlyMap<string, SandboxBlock>;
  readonly nestedSandboxIds: ReadonlySet<string>;
}

type RenderSegment =
  | { kind: "single"; block: TurnProcessBlock }
  | {
      kind: "workflow";
      tools: ToolBlock[];
      thinkingMs: number;
      /** Non-tool blocks interleaved in the tool run (thinking between tools). */
      interleaved: TurnProcessBlock[];
    };

/**
 * Partition process into single blocks vs multi-tool WorkflowCollapse segments.
 * LobeHub: multi-tool → WorkflowCollapse; single tool → inline ToolCallCard.
 */
export function partitionProcessSegments(
  blocks: readonly TurnProcessBlock[],
): RenderSegment[] {
  const segments: RenderSegment[] = [];
  let i = 0;

  while (i < blocks.length) {
    const b = blocks[i]!;

    // Tool/sandbox cluster — thinking stays as its own row (LobeHub: 已深度思考 before 工具)
    if (b.kind === "tool" || b.kind === "sandbox") {
      const cluster: TurnProcessBlock[] = [];
      while (i < blocks.length) {
        const cur = blocks[i]!;
        if (cur.kind === "tool" || cur.kind === "sandbox") {
          cluster.push(cur);
          i += 1;
          continue;
        }
        break;
      }

      const tools = cluster.filter((c): c is ToolBlock => c.kind === "tool");
      const thinkingMs = blocks
        .filter((c): c is ThinkingBlock => c.kind === "thinking")
        .reduce((s, t) => s + (t.durationMs ?? 0), 0);

      if (tools.length >= WORKFLOW_MULTI_TOOL_THRESHOLD) {
        segments.push({
          kind: "workflow",
          tools,
          thinkingMs,
          interleaved: cluster,
        });
      } else {
        for (const c of cluster) {
          segments.push({ kind: "single", block: c });
        }
      }
      continue;
    }

    if (b.kind === "thinking") {
      segments.push({ kind: "single", block: b });
      i += 1;
      continue;
    }

    segments.push({ kind: "single", block: b });
    i += 1;
  }

  return segments;
}

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
    case "activity":
      return <ActivityCard key={block.id} block={block as ActivityBlock} />;
    default:
      return null;
  }
}

function buildContext(blocks: readonly TurnProcessBlock[]): BlockRenderContext {
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
  return { sandboxesByInvocation, nestedSandboxIds };
}

/** Render ordered process blocks with WorkflowCollapse for multi-tool runs. */
export function ProcessBlocks({ blocks }: { readonly blocks: readonly TurnProcessBlock[] }) {
  const ctx = buildContext(blocks);
  const segments = partitionProcessSegments(blocks);

  return (
    <div className="grid gap-2.5">
      {segments.map((seg, idx) => {
        if (seg.kind === "workflow") {
          const key = `wf-${seg.tools[0]?.id ?? idx}`;
          return (
            <WorkflowCollapse
              key={key}
              tools={seg.tools}
              thinkingDurationMs={seg.thinkingMs || undefined}
            >
              {seg.interleaved.map((block) => {
                if (block.kind === "sandbox" && ctx.nestedSandboxIds.has(block.invocationId)) {
                  return null;
                }
                return renderProcessBlock(block, ctx);
              })}
            </WorkflowCollapse>
          );
        }
        return renderProcessBlock(seg.block, ctx);
      })}
    </div>
  );
}
