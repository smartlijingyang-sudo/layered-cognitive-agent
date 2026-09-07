// LCA-P1: HTTP entry point for starting an LCA run.
//
// Mirrors the run-receipt shape from
// `lca/plugins/transport/webserver/handlers/runs/api/command_endpoints.py`:
//   { run_id, trace_id, agent, ws_token }
// The native gateway execute.ts pulls run_id from a session creation
// step (tRPC), we get it from a plain HTTP POST to /lca-api/runs.

import type { LcaRunReceipt } from './types';

export interface LcaStartRunBody {
  agent: { id: string; name: string };
  messages: Array<{ role: 'user' | 'assistant' | 'system'; content: string }>;
  parent_message_id?: string;
  topic_id?: string;
  resume_approval?: {
    approvalId: string;
    parentMessageId: string;
    rejectionReason?: string;
    toolCallId: string;
  };
  resume_tool_result?: {
    content: string;
    parentMessageId: string;
    toolCallId: string;
    pluginState?: Record<string, unknown>;
  };
}

export interface LcaStartRunResult extends LcaRunReceipt {
  runId: string;
  token: string;
  operationId: string;
}

const TOKEN_HEADER_NAME = 'X-Lca-Token';

function bearer(): string {
  const envToken =
    typeof process !== 'undefined'
      ? (process as { env?: Record<string, string | undefined> }).env
          ?.NEXT_PUBLIC_LCA_TOKEN
      : undefined;
  return envToken && envToken.length > 0 ? envToken : 'lca-local';
}

export async function lcaStartRun(
  body: LcaStartRunBody,
  fetchImpl: typeof fetch = fetch,
): Promise<LcaStartRunResult> {
  const resp = await fetchImpl('/lca-api/runs', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${bearer()}`,
      [TOKEN_HEADER_NAME]: bearer(),
    },
    body: JSON.stringify({
      agent: body.agent,
      messages: body.messages,
      ...(body.parent_message_id ? { parent_message_id: body.parent_message_id } : {}),
      ...(body.topic_id ? { topic_id: body.topic_id } : {}),
      ...(body.resume_approval ? { resume_approval: body.resume_approval } : {}),
      ...(body.resume_tool_result ? { resume_tool_result: body.resume_tool_result } : {}),
    }),
  });
  if (!resp.ok) {
    throw new Error(`lca /runs HTTP ${resp.status}`);
  }
  const receipt = (await resp.json()) as LcaRunReceipt;
  return {
    ...receipt,
    runId: receipt.run_id,
    token: receipt.ws_token,
    operationId: receipt.run_id,
  };
}