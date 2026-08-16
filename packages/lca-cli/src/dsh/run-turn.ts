import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { createInterface } from 'node:readline';
import fs from 'node:fs';

import type { GatewayClient } from '@lca/gateway-client';

const WORKER_KIND_ERROR = 'error';
const WORKER_KIND_FINISHED = 'finished';
const WORKER_KIND_NOTIFICATION = 'notification';

const activeTurns = new Map<string, ChildProcessWithoutNullStreams>();

function spawnWorker(
  python: string,
  configJson: string,
): ChildProcessWithoutNullStreams {
  return spawn(python, ['-m', 'lca.layer0_infra.dsh.daemon_worker', configJson], {
    stdio: ['pipe', 'pipe', 'pipe'],
    env: {
      ...process.env,
      PYTHONPATH: process.env['PYTHONPATH'] ?? '/opt/lca/python',
      LCA_PYTHON: python,
    },
  }) as ChildProcessWithoutNullStreams;
}

function resolvePython(): string {
  const candidates = [
    process.env['LCA_PYTHON'],
    '/opt/lca/venv/bin/python3',
    'python3',
  ];
  for (const candidate of candidates) {
    if (candidate && (candidate.includes('/') ? fs.existsSync(candidate) : true)) {
      return candidate;
    }
  }
  return 'python3';
}

export async function executeDshTurn(
  client: GatewayClient,
  turnId: string,
  params: Record<string, unknown>,
): Promise<void> {
  const python = resolvePython();
  const configJson = JSON.stringify(params);
  const child = spawnWorker(python, configJson);
  activeTurns.set(turnId, child);

  const finish = (result: {
    success: boolean;
    session_id?: string;
    final_response?: string;
    finish_reason?: string | null;
    error?: string;
  }) => {
    activeTurns.delete(turnId);
    client.sendDshTurnFinished(turnId, result);
  };

  child.stderr.on('data', (chunk: Buffer) => {
    console.error(`[dsh ${turnId}] ${chunk.toString('utf8')}`);
  });

  child.on('error', (error) => {
    finish({ success: false, error: error.message });
  });

  child.on('close', (code) => {
    if (activeTurns.has(turnId)) {
      finish({ success: false, error: `worker exited with code ${code ?? 'unknown'}` });
    }
  });

  const lines = createInterface({ input: child.stdout });
  try {
    for await (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(trimmed) as Record<string, unknown>;
      } catch {
        console.warn(`[dsh ${turnId}] invalid worker line: ${trimmed.slice(0, 120)}`);
        continue;
      }
      const kind = String(msg['kind'] ?? '');
      if (kind === WORKER_KIND_NOTIFICATION) {
        client.sendDshNotification(
          turnId,
          String(msg['method'] ?? ''),
          (msg['payload'] as Record<string, unknown>) ?? {},
        );
        continue;
      }
      if (kind === WORKER_KIND_ERROR) {
        child.kill('SIGTERM');
        finish({ success: false, error: String(msg['message'] ?? 'DSH worker error') });
        return;
      }
      if (kind === WORKER_KIND_FINISHED) {
        activeTurns.delete(turnId);
        client.sendDshTurnFinished(turnId, {
          success: true,
          session_id: String(msg['session_id'] ?? turnId),
          final_response: String(msg['final_response'] ?? ''),
          finish_reason: (msg['finish_reason'] as string | null | undefined) ?? null,
        });
        return;
      }
    }
    if (activeTurns.has(turnId)) {
      finish({ success: false, error: 'worker closed stdout without finished event' });
    }
  } finally {
    lines.close();
  }
}

export function cancelDshTurn(turnId: string): void {
  const child = activeTurns.get(turnId);
  if (!child) return;
  activeTurns.delete(turnId);
  child.kill('SIGTERM');
}
