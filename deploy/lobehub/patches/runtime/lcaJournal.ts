/** Live SSE (four events) → projection values. No store I/O. */

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
  | { kind: 'run-finished'; error?: string; status?: string }
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

function parseToolDetailArgs(detail: unknown): Record<string, unknown> {
  if (typeof detail !== 'string' || !detail.startsWith('{')) return {};
  try {
    const parsed = JSON.parse(detail) as unknown;
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : {};
  } catch {
    return {};
  }
}

/** Map ADR-0100 four live SSE events to LobeHub row projections. */
export function projectJournalFrame(frame: JournalFrame): Projected {
  const payload = frame.eventPayload ?? {};
  switch (frame.event) {
    case 'reasoning':
      return { kind: 'reasoning', text: String(payload.text ?? '') };
    case 'text':
      return { kind: 'text', text: String(payload.text ?? '') };
    case 'tool': {
      const phase = String(payload.phase ?? '');
      const toolName = String(payload.name ?? '');
      const baseState =
        payload.state && typeof payload.state === 'object' && !Array.isArray(payload.state)
          ? (payload.state as Record<string, unknown>)
          : {};
      if (phase === 'started') {
        return {
          idHint: String(payload.id ?? `call_${frame.seq ?? 0}`),
          kind: 'tool-start',
          state: { ...baseState, ...parseToolDetailArgs(payload.detail) },
          toolName,
        };
      }
      if (phase === 'done') {
        const outText = typeof payload.detail === 'string' ? payload.detail : '';
        const outputAliases =
          outText && outText !== 'ok' ? { output: outText, stdout: outText, content: outText } : {};
        return {
          files: payload.files,
          kind: 'tool-invoked',
          payload,
          state: { ...baseState, ...outputAliases },
        };
      }
      if (phase === 'denied') {
        return {
          kind: 'tool-denied',
          payload,
          reason: String(payload.detail ?? payload.error ?? 'denied'),
        };
      }
      return { kind: 'ignore' };
    }
    case 'done':
      return {
        error: payload.error ? String(payload.error) : undefined,
        kind: 'run-finished',
        status: typeof payload.status === 'string' ? payload.status : undefined,
      };
    case 'LiveGap':
      return { kind: 'live-gap' };
    default:
      return { kind: 'ignore' };
  }
}
