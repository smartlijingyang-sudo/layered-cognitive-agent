/** Journal SSE → projection values. No store I/O. */

export type JournalFrame = {
  event: string;
  eventPayload?: Record<string, unknown>;
  seq?: number;
  speaker?: string;
};

export type Projected =
  | { kind: 'ignore' }
  | { kind: 'open-turn'; speaker: string }
  | { kind: 'reasoning'; text: string }
  | { kind: 'reasoning-end'; durationMs?: number }
  | { kind: 'text'; text: string }
  | { kind: 'tool-start'; idHint: string; state: Record<string, unknown>; toolName: string }
  | { kind: 'sandbox-delta'; payload: Record<string, unknown>; stream: string; text: string }
  | {
      files: unknown;
      kind: 'tool-invoked';
      payload: Record<string, unknown>;
      state: Record<string, unknown>;
    }
  | { kind: 'tool-denied'; payload: Record<string, unknown>; reason: string }
  | { kind: 'run-finished'; error?: string }
  | { kind: 'live-gap' };

export function toolCallId(payload: Record<string, unknown>, fallback: string): string {
  const invocation = payload.invocation_id;
  if (typeof invocation === 'string' && invocation) return invocation;
  const toolCall = payload.tool_call_id;
  if (typeof toolCall === 'string' && toolCall) return toolCall;
  return fallback;
}

export function parseSseBlock(block: string): JournalFrame | null {
  let eventName = '';
  let idLine = '';
  const dataLines: string[] = [];
  for (const line of block.split('\n')) {
    if (line.startsWith('id:') || line.startsWith('id: ')) idLine = line.replace(/^id:\s?/, '').trim();
    else if (line.startsWith('event:') || line.startsWith('event: '))
      eventName = line.replace(/^event:\s?/, '').trim();
    else if (line.startsWith('data:') || line.startsWith('data: '))
      dataLines.push(line.replace(/^data:\s?/, ''));
  }
  if (!eventName || !dataLines.length) return null;
  try {
    const parsed = JSON.parse(dataLines.join('\n')) as Record<string, unknown>;
    // ADR-0096 MVA-1 / 5204fd56 follow-up: v2 envelope 顶层字段从 data → payload (v2.0.0);
    // 兼容 lca.journal/2 disk/SSE envelope（payload 在 data 下）与 Session Spine deltas
    // 通道（SessionEvent 嵌 envelope.event）。按优先级尝试三种来源。
    const payload = (parsed.payload ?? parsed.data) as Record<string, unknown> | undefined;
    const inner =
      payload && typeof payload === 'object'
        ? payload
        : parsed.event && typeof parsed.event === 'object'
          ? (parsed.event as Record<string, unknown>)
          : parsed;
    const scope =
      parsed.scope && typeof parsed.scope === 'object'
        ? (parsed.scope as Record<string, unknown>)
        : {};
    const seqFromId = Number(idLine);
    return {
      event: eventName,
      eventPayload: inner,
      seq:
        typeof parsed.seq === 'number'
          ? parsed.seq
          : Number.isFinite(seqFromId)
            ? seqFromId
            : undefined,
      speaker: typeof scope.agent_role === 'string' ? scope.agent_role : '',
    };
  } catch {
    return null;
  }
}

export function projectJournalFrame(frame: JournalFrame): Projected {
  const payload = frame.eventPayload ?? {};
  switch (frame.event) {
    case 'LlmCallStarted':
      return { kind: 'open-turn', speaker: frame.speaker ?? '' };
    case 'ReasoningDelta':
      return { kind: 'reasoning', text: String(payload.text_delta ?? '') };
    case 'ReasoningCompleted': {
      const raw = payload.duration_ms;
      const durationMs = typeof raw === 'number' && Number.isFinite(raw) ? raw : undefined;
      return { durationMs, kind: 'reasoning-end' };
    }
    case 'StepTextDelta':
      if (payload.channel && payload.channel !== 'answer') return { kind: 'ignore' };
      return { kind: 'text', text: String(payload.text_delta ?? '') };
    case 'ToolCallStreaming':
    case 'ToolStarted': {
      // ADR-0101 PR-2: tool events return to facts. ``arguments`` lives at
      // payload.arguments (top-level fact), not in plugin_state. Merge it
      // into the projected state so pickArgs / mergeInvocationArgs in
      // LcaRunDriver find it; the renderer also reads args from there.
      const baseState =
        (payload.plugin_state as Record<string, unknown> | undefined) ?? {};
      const rawArgs = payload.arguments;
      const merged =
        rawArgs && typeof rawArgs === 'object' && !Array.isArray(rawArgs)
          ? { ...baseState, ...(rawArgs as Record<string, unknown>) }
          : baseState;
      return {
        idHint: toolCallId(payload, `call_${frame.seq ?? 0}`),
        kind: 'tool-start',
        state: merged,
        toolName: String(payload.tool_name ?? ''),
      };
    }
    case 'SandboxOutputDelta':
      return {
        kind: 'sandbox-delta',
        payload,
        stream: String(payload.stream ?? 'stdout'),
        text: String(payload.text_delta ?? ''),
      };
    case 'ToolInvoked': {
      // ADR-0101 PR-2: output_text is the top-level fact for tool output
      // (no longer nested under plugin_state.output). Renderers read
      // pluginState.output / .stdout / .content; expose output_text under
      // all three keys so per-tool renders and the generic toolCardContent
      // helper both find it. Keep the original plugin_state fields first
      // so renderer-specific structured data (e.g. skill metadata in
      // activate_skill) still wins on key collision.
      const baseState =
        (payload.plugin_state as Record<string, unknown> | undefined) ?? {};
      const outText = payload.output_text;
      const projState =
        payload.projected_state &&
        typeof payload.projected_state === 'object' &&
        !Array.isArray(payload.projected_state)
          ? (payload.projected_state as Record<string, unknown>)
          : {};
      const outputAliases =
        typeof outText === 'string' && outText.length > 0
          ? { output: outText, stdout: outText, content: outText }
          : {};
      return {
        files: payload.files,
        kind: 'tool-invoked',
        payload,
        state: { ...baseState, ...outputAliases, ...projState },
      };
    }
    case 'ToolDenied':
      return {
        kind: 'tool-denied',
        payload,
        reason: String(payload.reason ?? payload.error ?? 'denied'),
      };
    case 'AgentRunFinished':
    case 'TeamRunFinished':
      return {
        error: payload.error ? String(payload.error) : undefined,
        kind: 'run-finished',
      };
    case 'LiveGap':
      return { kind: 'live-gap' };
    default:
      return { kind: 'ignore' };
  }
}
