/**
 * Run command face (ADR-0100 C7).
 *
 * POST /runs, cancel, and wire serialization — never mixed with live SSE observe.
 */

import type { UIChatMessage } from '@lobechat/types';

import { useAgentStore } from '@/store/agent';
import { agentByIdSelectors } from '@/store/agent/selectors';

export const LCA_TOKEN = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';

export type WireFile = {
  id?: string;
  mime_type?: string;
  name: string;
  size?: number;
  url: string;
};

export type WireMessage = {
  content: string;
  files?: WireFile[];
  role: string;
};

export type CreateRunResult = {
  live_url?: string;
  run_id: string;
  trace_id: string;
};

export type CreateRunBody = {
  agent: { id: string; name: string };
  assistant_id?: string;
  device_id?: string;
  execution_target?: string;
  messages: WireMessage[];
  model: string;
  plane?: string;
};

export function lcaAuthHeaders(token: string = LCA_TOKEN): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

export function planeFieldsFromAgent(agentId: string | undefined): {
  assistant_id?: string;
  device_id?: string;
  plane?: string;
  execution_target?: string;
} {
  if (!agentId) return {};
  const config = agentByIdSelectors.getAgencyConfigById(agentId)(useAgentStore.getState());
  const lcaAssistantId = (config as { lcaAssistantId?: string } | undefined)?.lcaAssistantId;
  const target = config?.executionTarget;
  const deviceId = config?.boundDeviceId;
  const assistantFields = lcaAssistantId ? { assistant_id: lcaAssistantId } : {};
  if (target === 'local' || target === 'device') {
    return deviceId
      ? { device_id: deviceId, plane: 'machine', execution_target: 'device', ...assistantFields }
      : { plane: 'machine', execution_target: 'device', ...assistantFields };
  }
  if (target === 'sandbox') return { plane: 'sandbox', execution_target: 'sandbox', ...assistantFields };
  if (target === 'auto') return { execution_target: 'auto', ...assistantFields };
  if (target === 'none') return { execution_target: 'none', ...assistantFields };
  return { ...assistantFields };
}

function collectWireFiles(message: UIChatMessage): WireFile[] {
  const out: WireFile[] = [];
  for (const file of message.fileList ?? []) {
    if (!file?.url || file.inaccessible) continue;
    out.push({
      id: file.id,
      mime_type: file.fileType,
      name: file.name,
      size: file.size,
      url: file.url,
    });
  }
  for (const image of message.imageList ?? []) {
    if (!image?.url) continue;
    out.push({
      id: image.id,
      mime_type: 'image/png',
      name: image.alt || image.id,
      url: image.url,
    });
  }
  return out;
}

export function toWireMessages(messages: UIChatMessage[]): WireMessage[] {
  return messages
    .filter(
      (message) =>
        message.role === 'user' || message.role === 'assistant' || message.role === 'system',
    )
    .map((message) => {
      const files = collectWireFiles(message);
      return {
        content: typeof message.content === 'string' ? message.content : '',
        role: message.role,
        ...(files.length ? { files } : {}),
      };
    });
}

/** One user message → one POST /runs (ADR-0100). */
export async function createLcaRun(
  body: CreateRunBody,
  signal: AbortSignal,
): Promise<CreateRunResult> {
  const response = await fetch('/lca-api/runs', {
    body: JSON.stringify(body),
    headers: {
      ...lcaAuthHeaders(),
      'Content-Type': 'application/json',
    },
    method: 'POST',
    signal,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`create run HTTP ${response.status}: ${text.slice(0, 200)}`);
  }
  return (await response.json()) as CreateRunResult;
}

export async function cancelLcaRun(
  runId: string,
  signal?: AbortSignal,
): Promise<void> {
  await fetch(`/lca-api/runs/${runId}/cancel`, {
    headers: lcaAuthHeaders(),
    method: 'POST',
    signal,
  }).catch(() => undefined);
}
