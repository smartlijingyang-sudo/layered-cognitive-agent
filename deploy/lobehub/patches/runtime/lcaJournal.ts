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

/**
 * ADR-0065 §四 state_ref-first read for Tool* events.
 *
 * Order of precedence (v2 envelope):
 * 1. ``state_ref`` (typed field) — payload lives in EvidenceStore at
 *    ``/runs/{id}/evidence/{ref}``; this function returns a state marker
 *    that the consuming React component (``ExecuteCodeRender``,
 *    ``RunCommandRender``) resolves asynchronously.
 * 2. typed fields — ``code`` / ``command`` / ``language`` / ``skill_id`` /
 *    ``description`` / ``execution_env`` / ``output_text``. These are
 *    LobeHub-renderable directly without an evidence fetch.
 * 3. legacy ``plugin_state`` (view-only, pre-flip) — fall through so
 *    older replays still render. The disk writer no longer produces this
 *    (0065 §四 stripping) but reads must keep working.
 */
export function buildToolState(
  payload: Record<string, unknown>,
  frame: JournalFrame,
): Record<string, unknown> {
  const state: Record<string, unknown> = {};
  // (1) state_ref first — read by hydration layer via /runs/{id}/evidence/{ref}
  const stateRef = payload.state_ref;
  if (stateRef && typeof stateRef === 'object') {
    state.__state_ref__ = stateRef;
  }
  // (2) typed fields (LobeHub-renderable directly)
  for (const key of [
    'code',
    'command',
    'language',
    'skill_id',
    'description',
    'execution_env',
    'output_text',
  ]) {
    const value = payload[key];
    if (typeof value === 'string' && value) state[key] = value;
  }
  const skillInputs = payload.skill_inputs;
  if (skillInputs && typeof skillInputs === 'object') {
    state.skill_inputs = skillInputs;
  }
  // (3) legacy plugin_state fallback (only when neither typed nor state_ref provided)
  if (Object.keys(state).length === 0 || (!('__state_ref__' in state) && !state.code && !state.command)) {
    const legacy = payload.plugin_state;
    if (legacy && typeof legacy === 'object') {
      Object.assign(state, legacy);
    }
  }
  return state;
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
        // ADR-0065 §四: read ``payload.state_ref`` first; if present, the
        // lobehub UI patch will fetch the typed fields + evidence payload
        // via /runs/{id}/evidence/{ref}. Falls back to legacy plugin_state
        // for pre-flip replays; the React component fills typed defaults
        // (code / command / language / skill_id / description / execution_env)
        // from the typed fields present on the event.
        state: buildToolState(payload, frame),
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
        // ADR-0065 §四: same state_ref-first read; see ToolStarted case.
        state: buildToolState(payload, frame),
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
