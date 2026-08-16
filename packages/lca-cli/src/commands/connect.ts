import { randomUUID } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';

import { GatewayClient } from '@lca/gateway-client';

import { checkEnvironment, formatReport } from '../tools/env-check.js';
import { executeToolCall } from '../tools/index.js';
import { cancelDshTurn, executeDshTurn } from '../dsh/run-turn.js';

const STATE_DIR = path.join(os.homedir(), '.lca');
const PID_FILE = path.join(STATE_DIR, 'connect.pid');
const CONNECTION_FILE = path.join(STATE_DIR, 'connection-id');
const DEVICE_FILE = path.join(STATE_DIR, 'device-id');

export type ConnectOptions = {
  gateway: string;
  token?: string;
  tokenType: string;
  workspace: string;
  daemon?: boolean;
};

function loadOrCreate(file: string): string {
  fs.mkdirSync(STATE_DIR, { recursive: true });
  if (fs.existsSync(file)) return fs.readFileSync(file, 'utf8').trim();
  const id = randomUUID();
  fs.writeFileSync(file, id, 'utf8');
  return id;
}

export async function connect(options: ConnectOptions): Promise<void> {
  if (options.daemon) {
    spawnDaemon(options);
    return;
  }

  // Environment self-check — surface missing tools before connecting.
  const envReport = await checkEnvironment();
  console.log(formatReport(envReport));
  if (!envReport.allOk) {
    console.warn('⚠️  Some tools are missing. Agent commands that need them will fail.');
    console.warn('   Run scripts/setup_host_runtime.sh or install the missing tools.');
  }

  const token = options.token || process.env['LCA_DEVICE_SERVICE_TOKEN'] || 'lca-local-host';
  const client = new GatewayClient({
    deviceId: loadOrCreate(DEVICE_FILE),
    connectionId: loadOrCreate(CONNECTION_FILE),
    gatewayUrl: options.gateway,
    token,
    tokenType: options.tokenType as 'serviceToken' | 'jwt' | 'apiKey',
    channel: 'cli',
    workspace: options.workspace,
    logger: console,
  });

  client.on('tool_call_request', async (request) => {
    const result = await executeToolCall(
      request.toolCall.apiName,
      request.toolCall.arguments,
      options.workspace,
    );
    client.sendToolCallResponse(request.requestId, result);
  });

  client.on('rpc_request', async (request) => {
    if (request.method === 'systemInfo') {
      const envReport = await checkEnvironment();
      client.sendRpcResponse(request.requestId, {
        success: true,
        data: {
          hostname: os.hostname(),
          platform: process.platform,
          home: os.homedir(),
          workspace: options.workspace,
          environment: {
            checks: envReport.checks,
            allOk: envReport.allOk,
            path: envReport.path,
          },
        },
      });
      return;
    }
    client.sendRpcResponse(request.requestId, {
      success: false,
      error: `unknown rpc ${request.method}`,
    });
  });

  client.on('dsh_run_turn_request', (request) => {
    void executeDshTurn(client, request.turnId, request.params).catch((error: unknown) => {
      const message = error instanceof Error ? error.message : String(error);
      client.sendDshTurnFinished(request.turnId, { success: false, error: message });
    });
  });

  client.on('dsh_cancel_turn', (request) => {
    cancelDshTurn(request.turnId);
  });

  await client.connect();
  console.log(`connected to ${options.gateway}`);
}

function spawnDaemon(options: ConnectOptions): void {
  fs.mkdirSync(STATE_DIR, { recursive: true });
  const args = [
    process.argv[1]!,
    'connect',
    '--gateway', options.gateway,
    '--workspace', options.workspace,
    '--token-type', options.tokenType,
  ];
  if (options.token) {
    args.push('--token', options.token);
  }
  const child = spawn(process.execPath, args, {
    detached: true,
    stdio: 'ignore',
    env: {
      ...process.env,
      'LCA_DEVICE_SERVICE_TOKEN': options.token || process.env['LCA_DEVICE_SERVICE_TOKEN'] || '',
    },
  });
  child.unref();
  if (child.pid) fs.writeFileSync(PID_FILE, String(child.pid), 'utf8');
  console.log(`daemon pid ${child.pid}`);
}

export async function stop(): Promise<void> {
  if (!fs.existsSync(PID_FILE)) {
    console.log('not running');
    return;
  }
  const pid = Number(fs.readFileSync(PID_FILE, 'utf8'));
  try {
    process.kill(pid, 'SIGTERM');
  } catch {
    // already gone
  }
  fs.rmSync(PID_FILE, { force: true });
}

export async function status(): Promise<void> {
  if (!fs.existsSync(PID_FILE)) {
    console.log('stopped');
    return;
  }
  const pid = fs.readFileSync(PID_FILE, 'utf8').trim();
  console.log(`running pid=${pid}`);
}
