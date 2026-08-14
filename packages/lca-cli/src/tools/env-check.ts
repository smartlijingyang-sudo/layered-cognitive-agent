/**
 * Environment self-check — runs on daemon startup to surface missing tools
 * before the first agent request arrives.
 *
 * Checks:
 *   1. python3 is on PATH and >= 3.10
 *   2. node is on PATH and >= 18
 *   3. system CLI tools (curl, wget, jq, git, ffmpeg, pandoc)
 *   4. shared venv at /opt/lca/venv has key packages importable
 *   5. officecli is available
 */
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const execFileAsync = promisify(execFile);

export type CheckItem = {
  name: string;
  ok: boolean;
  detail: string;
};

export type EnvReport = {
  platform: string;
  hostname: string;
  user: string;
  path: string;
  checks: CheckItem[];
  allOk: boolean;
};

const VENV_DIR = '/opt/lca/venv';

const SYSTEM_TOOLS = [
  'curl', 'wget', 'jq', 'git', 'ffmpeg', 'pandoc',
] as const;

const PYTHON_PACKAGES = [
  'pandas', 'numpy', 'matplotlib', 'openpyxl', 'reportlab',
  'requests', 'PIL', 'plotly', 'scipy', 'docx',
] as const;

async function checkVersion(
  cmd: string,
  args: string[],
  parse: (stdout: string) => string,
): Promise<{ version: string; path: string }> {
  const { stdout } = await execFileAsync(cmd, args, { timeout: 5000 });
  return { version: parse(stdout.trim()), path: cmd };
}

async function safeCheck(fn: () => Promise<CheckItem>): Promise<CheckItem> {
  try {
    return await fn();
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    return { name: 'unknown', ok: false, detail: msg };
  }
}

export async function checkEnvironment(): Promise<EnvReport> {
  const checks: CheckItem[] = [];

  // 1. python3
  checks.push(await safeCheck(async () => {
    const { version, path: binPath } = await checkVersion(
      'python3', ['--version'],
      (s) => s.replace(/^Python\s+/, ''),
    );
    const [major, minor] = version.split('.').map(Number);
    const ok = major >= 3 && minor >= 10;
    return {
      name: 'python3',
      ok,
      detail: ok
        ? `${version} @ ${binPath}`
        : `${version} @ ${binPath} — need >= 3.10`,
    };
  }));

  // 2. node
  checks.push(await safeCheck(async () => {
    const { version, path: binPath } = await checkVersion(
      'node', ['--version'],
      (s) => s.replace(/^v/, ''),
    );
    const major = Number(version.split('.')[0]);
    const ok = major >= 18;
    return {
      name: 'node',
      ok,
      detail: ok
        ? `v${version} @ ${binPath}`
        : `v${version} @ ${binPath} — need >= 18`,
    };
  }));

  // 3. system CLI tools
  for (const tool of SYSTEM_TOOLS) {
    checks.push(await safeCheck(async () => {
      try {
        const { stdout } = await execFileAsync('which', [tool], { timeout: 3000 });
        return { name: tool, ok: true, detail: stdout.trim() };
      } catch {
        return { name: tool, ok: false, detail: 'not found in PATH' };
      }
    }));
  }

  // 4. shared venv packages
  checks.push(await safeCheck(async () => {
    const venvPython = `${VENV_DIR}/bin/python3`;
    try {
      await fs.access(venvPython);
    } catch {
      return { name: 'venv', ok: false, detail: `${VENV_DIR} not found` };
    }
    const imports = PYTHON_PACKAGES.map((p) => `import ${p}`).join('; ');
    try {
      await execFileAsync(venvPython, ['-c', imports], { timeout: 10000 });
      return { name: 'venv-packages', ok: true, detail: `${PYTHON_PACKAGES.length} packages importable` };
    } catch (error) {
      const msg = error instanceof Error ? error.message.slice(0, 200) : String(error);
      return { name: 'venv-packages', ok: false, detail: msg };
    }
  }));

  // 5. officecli
  checks.push(await safeCheck(async () => {
    try {
      const { stdout } = await execFileAsync('which', ['officecli'], { timeout: 3000 });
      return { name: 'officecli', ok: true, detail: stdout.trim() };
    } catch {
      return { name: 'officecli', ok: false, detail: 'not found in PATH' };
    }
  }));

  const allOk = checks.every((c) => c.ok);
  return {
    platform: os.platform(),
    hostname: os.hostname(),
    user: os.userInfo().username,
    path: process.env['PATH'] || '',
    checks,
    allOk,
  };
}

/** Format a human-readable summary for logging. */
export function formatReport(report: EnvReport): string {
  const lines: string[] = [
    `env-check: ${report.user}@${report.hostname} (${report.platform})`,
    `  PATH: ${report.path}`,
  ];
  for (const check of report.checks) {
    const icon = check.ok ? '✅' : '❌';
    lines.push(`  ${icon} ${check.name}: ${check.detail}`);
  }
  lines.push(report.allOk ? '  → all checks passed' : '  → SOME CHECKS FAILED');
  return lines.join('\n');
}
