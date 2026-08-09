import type { ReactElement } from "react";
import type { RunScope } from "../contracts";
import type { JournalEvent } from "../contracts";
import { domainColor } from "./domain-colors";
import { cn } from "../lib/cn";
import { mutedText } from "../lib/ui";

export interface EventRendererProps<E extends JournalEvent = JournalEvent> {
  readonly event: E;
  readonly scope: RunScope;
  readonly domain?: string;
}

export type EventRenderer = (props: EventRendererProps) => ReactElement | null;

function Card({
  title,
  body,
  domain,
}: {
  readonly title: string;
  readonly body: string;
  readonly domain?: string;
}) {
  const border = domainColor(domain as Parameters<typeof domainColor>[0]);
  return (
    <div
      className={cn(
        "rounded-[var(--radius-sm)] border-l-[3px] bg-[color-mix(in_srgb,var(--bg)_65%,transparent)] px-3 py-2",
      )}
      style={{ borderLeftColor: border }}
    >
      <div className="text-sm font-semibold">{title}</div>
      <div className={cn("mt-0.5 text-sm whitespace-pre-wrap", mutedText)}>{body}</div>
    </div>
  );
}

export function CastingStartedCard({ event, domain }: EventRendererProps) {
  if (event.type !== "CastingStarted") return null;
  return (
    <Card
      domain={domain}
      title="◎ 智能选角"
      body={`正在分析问题并挑选角色…\n${event.objective_preview}`}
    />
  );
}

export function CastingCompletedCard({ event, domain }: EventRendererProps) {
  if (event.type !== "CastingCompleted") return null;
  const roles = event.selected_roles.join("、");
  const lead = event.lead_role ? `\n主导：${event.lead_role}` : "";
  return (
    <Card
      domain={domain}
      title="✓ 组队完成"
      body={`协作方式：${event.governance_kind}${lead}\n成员：${roles}${event.rationale ? `\n${event.rationale}` : ""}`}
    />
  );
}

export function CastingFailedCard({ event, domain }: EventRendererProps) {
  if (event.type !== "CastingFailed") return null;
  return <Card domain={domain} title="✗ 组队失败" body={event.error} />;
}

export function DelegationCard({ event, domain }: EventRendererProps) {
  if (event.type !== "DelegationIssued") return null;
  return (
    <Card
      domain={domain}
      title={`⇢ 委派 → ${event.callee_role}`}
      body={event.subtask_preview || "(无预览)"}
    />
  );
}

export function DecisionCard({ event, domain }: EventRendererProps) {
  if (event.type !== "DecisionMade") return null;
  const target = event.delegate_target ? ` → ${event.delegate_target}` : "";
  return (
    <Card
      domain={domain}
      title={`决策 · step ${event.step}`}
      body={`${event.action_type}${target} · 置信 ${(event.confidence * 100).toFixed(0)}%`}
    />
  );
}

export function ToolStartedCard({ event, domain }: EventRendererProps) {
  if (event.type !== "ToolStarted") return null;
  return (
    <Card
      domain={domain}
      title={`工具开始 · ${event.tool_name}`}
      body={event.arguments_preview || event.invocation_id || "(running)"}
    />
  );
}

export function ToolCallCard({ event, domain }: EventRendererProps) {
  if (event.type !== "ToolInvoked") return null;
  return (
    <Card
      domain={domain}
      title={`工具 · ${event.tool_name}`}
      body={`${event.ok ? "ok" : "FAIL"} · ${event.latency_ms}ms`}
    />
  );
}

export function ReasoningDeltaCard({ event, domain }: EventRendererProps) {
  if (event.type !== "ReasoningDelta") return null;
  return (
    <Card domain={domain} title={`思考 Δ step ${event.step}`} body={event.text_delta || "(empty)"} />
  );
}

export function ReasoningCompletedCard({ event, domain }: EventRendererProps) {
  if (event.type !== "ReasoningCompleted") return null;
  return (
    <Card
      domain={domain}
      title={`思考完成 · step ${event.step}`}
      body={`${event.duration_ms}ms${event.content_preview ? `\n${event.content_preview}` : ""}`}
    />
  );
}

export function LlmCallStartedCard({ event, domain }: EventRendererProps) {
  if (event.type !== "LlmCallStarted") return null;
  return (
    <Card domain={domain} title={`LLM 开始 · ${event.model}`} body={`step ${event.step}`} />
  );
}

export function RunActivityCard({ event, domain }: EventRendererProps) {
  if (event.type !== "RunActivity") return null;
  return (
    <Card
      domain={domain}
      title={`活动 · ${event.phase}`}
      body={`step ${event.step} · ${event.detail}`}
    />
  );
}

export function LlmCallCard({ event, domain }: EventRendererProps) {
  if (event.type !== "LlmCallCompleted") return null;
  const tokens =
    event.prompt_tokens || event.completion_tokens
      ? ` · tokens ${event.prompt_tokens}/${event.completion_tokens}`
      : "";
  return (
    <Card
      domain={domain}
      title={`LLM · ${event.model}`}
      body={`${event.latency_ms}ms${tokens}${event.ok ? "" : " · FAIL"}${event.stream ? " · stream" : ""}`}
    />
  );
}

/** Registry 兜底：单条 raw delta。时间线应优先用 StepTextStreamCard。 */
export function StepTextDeltaCard({ event, domain }: EventRendererProps) {
  if (event.type !== "StepTextDelta") return null;
  return (
    <Card
      domain={domain}
      title={`Δ step ${event.step}`}
      body={event.text_delta || "(empty)"}
    />
  );
}

/** 合并后的 step 文本流（ADR-0041 轨迹投影）。 */
export function StepTextStreamCard({
  stream,
}: {
  readonly stream: import("../projectors").StepTextStream;
}) {
  const role = stream.agentRole ? ` · ${stream.agentRole}` : "";
  const chunks = stream.chunkCount > 1 ? ` · ${stream.chunkCount} chunks` : "";
  const border = domainColor(stream.domain as Parameters<typeof domainColor>[0]);
  return (
    <div
      className={cn(
        "rounded-[var(--radius-sm)] border-l-[3px] bg-[color-mix(in_srgb,var(--bg)_65%,transparent)] px-3 py-2",
      )}
      style={{ borderLeftColor: border }}
    >
      <div className="text-sm font-semibold">{`Δ step ${stream.step}${role}${chunks}`}</div>
      <div
        className={cn(
          "mt-0.5 max-h-48 overflow-auto text-sm whitespace-pre-wrap font-mono",
          mutedText,
        )}
      >
        {stream.text || "(empty)"}
      </div>
    </div>
  );
}

/** 沙箱 stdout/stderr 合并流（ADR-0044）；纯文本等宽，不引入终端模拟器。 */
export function SandboxOutputStreamCard({
  stream,
}: {
  readonly stream: import("../projectors").SandboxOutputStream;
}) {
  const role = stream.agentRole ? ` · ${stream.agentRole}` : "";
  const status = stream.sealed ? " · done" : " · live";
  const label = stream.stream === "stderr" ? "stderr" : "stdout";
  const border = domainColor(stream.domain as Parameters<typeof domainColor>[0]);
  return (
    <div
      className={cn(
        "rounded-[var(--radius-sm)] border-l-[3px] bg-[color-mix(in_srgb,var(--bg)_65%,transparent)] px-3 py-2",
      )}
      style={{ borderLeftColor: border }}
    >
      <div className="text-sm font-semibold">
        {`沙箱 · ${label}${role}${status}`}
      </div>
      <pre
        className={cn(
          "mt-0.5 max-h-64 overflow-auto rounded bg-black/20 p-2 text-xs whitespace-pre-wrap font-mono",
          stream.stream === "stderr" ? "text-danger" : mutedText,
        )}
      >
        {stream.text || "(empty)"}
      </pre>
    </div>
  );
}

/** Registry 兜底：单条 sandbox raw delta。时间线应优先用 SandboxOutputStreamCard。 */
export function SandboxOutputDeltaCard({ event, domain }: EventRendererProps) {
  if (event.type !== "SandboxOutputDelta") return null;
  return (
    <Card
      domain={domain}
      title={`沙箱 Δ ${event.stream} · ${event.invocation_id}`}
      body={event.text_delta || "(empty)"}
    />
  );
}

export function InsightBadge({ event, domain }: EventRendererProps) {
  if (event.type !== "RunInsight") return null;
  return (
    <Card domain={domain} title={`洞察 · ${event.kind}`} body={event.summary || event.detail} />
  );
}

export function SynthesisCard({ event, domain }: EventRendererProps) {
  if (event.type !== "SynthesisCompleted") return null;
  return (
    <Card
      domain={domain}
      title={`◈ 收口综合 (${event.method})`}
      body={event.output_text || `${event.candidate_count} candidates`}
    />
  );
}

export function DelegationCompletedCard({ event, domain }: EventRendererProps) {
  if (event.type !== "DelegationCompleted") return null;
  return (
    <Card
      domain={domain}
      title={`⇠ 委派回执`}
      body={`${event.status} · ${event.output_text || ""}`}
    />
  );
}

export function ContainerCard({ event, domain }: EventRendererProps) {
  if (event.type === "TeamRunStarted") {
    return (
      <Card
        domain={domain}
        title={`团队 run · ${event.team_id}`}
        body={`${event.mandate} · 成员 ${event.members.join(", ")}`}
      />
    );
  }
  if (event.type === "AgentRunStarted") {
    return (
      <Card domain={domain} title={`Agent · ${event.agent_role}`} body={event.objective_preview} />
    );
  }
  if (event.type === "TeamRunFinished" || event.type === "AgentRunFinished") {
    return (
      <Card
        domain={domain}
        title={`run 结束 · ${event.status}`}
        body={event.output_text || `${event.steps} steps`}
      />
    );
  }
  if (event.type === "DelegationCacheHit") {
    return (
      <Card domain={domain} title="委派缓存命中" body={`${event.callee_role} · step ${event.step}`} />
    );
  }
  if (event.type === "StepCompleted") {
    return (
      <Card domain={domain} title={`步 ${event.step}`} body={`${event.action_type} · ${event.status}`} />
    );
  }
  if (event.type === "ActionDegraded") {
    return (
      <Card
        domain={domain}
        title="动作降级"
        body={`${event.original_action_type} → ${event.degraded_to}`}
      />
    );
  }
  if (event.type === "ToolDenied") {
    return <Card domain={domain} title={`工具拒绝 · ${event.tool_name}`} body={event.reason} />;
  }
  return null;
}
