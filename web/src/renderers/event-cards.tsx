import type { ReactElement } from "react";
import type { RunScope } from "../contracts";
import type { JournalEvent } from "../contracts";
import { domainColor } from "./domain-colors";

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
    <div className="event-card" style={{ borderLeftColor: border }}>
      <div className="event-card-title">{title}</div>
      <div className="event-card-body">{body}</div>
    </div>
  );
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
      body={`${event.latency_ms}ms${tokens}${event.ok ? "" : " · FAIL"}`}
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
