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
    const data = JSON.parse(dataLines.join('\n')) as Record<string, unknown>;
    const inner =
      data.event && typeof data.event === 'object' ? (data.event as Record<string, unknown>) : data;
    const scope =
      data.scope && typeof data.scope === 'object' ? (data.scope as Record<string, unknown>) : {};
    const seqFromId = Number(idLine);
    return {
      event: eventName,
      eventPayload: inner,
      seq: typeof data.seq === 'number' ? data.seq : Number.isFinite(seqFromId) ? seqFromId : undefined,
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
    case 'ToolStarted':
      return {
        idHint: toolCallId(payload, `call_${frame.seq ?? 0}`),
        kind: 'tool-start',
        state: (payload.plugin_state as Record<string, unknown> | undefined) ?? {},
        toolName: String(payload.tool_name ?? ''),
      };
    case 'SandboxOutputDelta':
      return {
        kind: 'sandbox-delta',
        payload,
        stream: String(payload.stream ?? 'stdout'),
        text: String(payload.text_delta ?? ''),
      };
    case 'ToolInvoked':
      return {
        files: payload.files,
        kind: 'tool-invoked',
        payload,
        state: (payload.plugin_state as Record<string, unknown> | undefined) ?? {},
      };
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
