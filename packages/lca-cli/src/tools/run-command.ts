import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

import { buildExecEnv } from './exec-env.js';
import { completedCommand, fromExecError, type ToolResult } from './shell-result.js';
import { resolveTimeoutMs } from './timeout.js';

const execFileAsync = promisify(execFile);

export async function runCommand(
  args: Record<string, unknown>,
  workspace: string,
): Promise<ToolResult> {
  const command = String(args['command'] || '');
  if (!command) {
    return { success: false, content: '', error: 'command is required' };
  }
  try {
    const { stdout, stderr } = await execFileAsync('/bin/sh', ['-c', command], {
      cwd: workspace,
      env: buildExecEnv(),
      timeout: resolveTimeoutMs(args),
    });
    return completedCommand({
      command,
      stdout: stdout ?? '',
      stderr: stderr ?? '',
      exitCode: 0,
    });
  } catch (error) {
    return fromExecError(error, command);
  }
}
