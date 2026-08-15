import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

import { buildExecEnv } from './exec-env.js';
import { completedCommand, fromExecError, type ToolResult } from './shell-result.js';
import { resolveTimeoutMs } from './timeout.js';

const execFileAsync = promisify(execFile);

export async function executeCode(
  args: Record<string, unknown>,
  workspace: string,
): Promise<ToolResult> {
  const code = String(args['code'] || '');
  const language = String(args['language'] || 'javascript');
  const env = buildExecEnv();
  const timeout = resolveTimeoutMs(args, 30);
  const isPython = language === 'python' || language === 'python3';
  const bin = isPython ? 'python3' : 'node';
  const flag = isPython ? '-c' : '-e';
  const command = `${bin} ${flag} <code>`;
  try {
    const { stdout, stderr } = await execFileAsync(bin, [flag, code], {
      cwd: workspace,
      env,
      timeout,
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
