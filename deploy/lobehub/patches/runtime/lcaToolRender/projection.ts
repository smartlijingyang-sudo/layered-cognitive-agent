/** Contract-driven ToolInvoked → LobeHub pluginState projection (ADR-0102). */

import { CONTRACTS, type ToolField } from './contracts.generated';

export type ProjectToolCallResult = {
  args: Record<string, unknown>;
  state: Record<string, unknown>;
  content: string | null;
};

const MISSING = Symbol('missing');

function readField(
  field: ToolField,
  args: Record<string, unknown>,
  obs: Record<string, unknown>,
): unknown | typeof MISSING {
  if (field.source === 'evidence_ref' || field.source === 'constant') {
    return MISSING;
  }
  if (field.source === 'argument') {
    return field.pythonKey in args ? args[field.pythonKey] : MISSING;
  }
  if (field.source === 'observation') {
    return field.pythonKey in obs ? obs[field.pythonKey] : MISSING;
  }
  return MISSING;
}

function projectArgs(toolName: string, args: Record<string, unknown>): Record<string, unknown> {
  const contract = CONTRACTS[toolName];
  if (!contract) return {};
  const result: Record<string, unknown> = {};
  for (const field of contract.args) {
    if (field.pythonKey in args) {
      result[field.wireKey] = args[field.pythonKey];
    }
  }
  return result;
}

function projectState(
  toolName: string,
  args: Record<string, unknown>,
  obs: Record<string, unknown>,
): Record<string, unknown> {
  const contract = CONTRACTS[toolName];
  if (!contract) return {};
  const result: Record<string, unknown> = {};
  for (const field of contract.state) {
    const value = readField(field, args, obs);
    if (value === MISSING) {
      if (field.required) continue;
      result[field.wireKey] = null;
    } else {
      result[field.wireKey] = value;
    }
  }
  return result;
}

function projectContent(toolName: string, obs: Record<string, unknown>): string | null {
  const contract = CONTRACTS[toolName];
  if (!contract?.contentField) return null;
  const value = obs[contract.contentField];
  return typeof value === 'string' ? value : null;
}

/**
 * Map a tool lifecycle pair to wire-shaped args/state/content.
 *
 * Priority:
 * 1. ``invokedData.projected_state`` (backend ``project_tool_state`` output)
 * 2. Contract-driven reconstruction from started args + invoked observation
 */
export function projectToolCall(
  toolName: string,
  startedData: Record<string, unknown> | undefined,
  invokedData: Record<string, unknown>,
): ProjectToolCallResult {
  const inlineState = invokedData.projected_state;
  if (inlineState && typeof inlineState === 'object' && !Array.isArray(inlineState)) {
    const projected = inlineState as Record<string, unknown>;
    const argsSource =
      (projected.args as Record<string, unknown> | undefined) ??
      projectArgs(toolName, startedData ?? {});
    const stateSource =
      (projected.state as Record<string, unknown> | undefined) ??
      (typeof projected === 'object' ? (projected as Record<string, unknown>) : {});
    return {
      args: argsSource,
      state: stateSource,
      content: (projected.content as string | null | undefined) ?? null,
    };
  }

  const args = startedData ?? {};
  const obs = { ...invokedData };
  return {
    args: projectArgs(toolName, args),
    state: projectState(toolName, args, obs),
    content: projectContent(toolName, obs),
  };
}
