/**
 * LobeHub local-file-shell semantics.
 *
 * ``success`` = the sidecar ran the command (spawned a process).
 * ``exitCode`` = the process status. Non-zero is a completed observation,
 * not a transport failure. Only spawn / timeout / policy are ``success: false``.
 */

export type ToolResult = {
  content: string;
  success: boolean;
  error?: string;
  stdout?: string;
  stderr?: string;
  output?: string;
  exitCode?: number | null;
  command?: string;
  timedOut?: boolean;
  path?: string;
  state?: unknown;
};

export function composeStreams(stdout: string, stderr: string): string {
  const out = stdout.replace(/\s+$/, '');
  const err = stderr.replace(/\s+$/, '');
  if (out && err) return `${out}\n${err}`;
  return out || err;
}

export function completedCommand(opts: {
  command: string;
  stdout: string;
  stderr: string;
  exitCode: number;
}): ToolResult {
  const content = composeStreams(opts.stdout, opts.stderr);
  return {
    success: true,
    content,
    stdout: opts.stdout,
    stderr: opts.stderr,
    output: opts.stdout || opts.stderr,
    exitCode: opts.exitCode,
    command: opts.command,
  };
}

type ExecLike = {
  message?: string;
  stdout?: string;
  stderr?: string;
  status?: number | null;
  killed?: boolean;
  signal?: NodeJS.Signals | null;
  code?: string | number;
};

export function fromExecError(error: unknown, command: string): ToolResult {
  const err = (error ?? {}) as ExecLike;
  const stdout = String(err.stdout ?? '');
  const stderr = String(err.stderr ?? '');
  const timedOut =
    Boolean(err.killed) || err.code === 'ETIMEDOUT' || err.signal === 'SIGTERM';
  if (timedOut) {
    const content = composeStreams(stdout, stderr) || `command timed out: ${command.slice(0, 200)}`;
    return {
      success: false,
      content,
      error: 'command timed out',
      stdout,
      stderr,
      output: stdout || stderr,
      exitCode: null,
      command,
      timedOut: true,
    };
  }
  const numeric =
    typeof err.status === 'number'
      ? err.status
      : typeof err.code === 'number'
        ? err.code
        : null;
  if (numeric !== null) {
    return completedCommand({ command, stdout, stderr, exitCode: numeric });
  }
  const message = typeof err.message === 'string' && err.message ? err.message : String(error);
  return {
    success: false,
    content: composeStreams(stdout, stderr) || message,
    error: message,
    stdout,
    stderr,
    command,
  };
}
