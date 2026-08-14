import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';

const STATE_DIR = path.join(os.homedir(), '.lca');
const PID_FILE = path.join(STATE_DIR, 'connect.pid');

export function ensureStateDir(): void {
  fs.mkdirSync(STATE_DIR, { recursive: true });
}

export function writePid(pid: number): void {
  ensureStateDir();
  fs.writeFileSync(PID_FILE, String(pid), 'utf8');
}

export function readPid(): number | null {
  if (!fs.existsSync(PID_FILE)) return null;
  const raw = fs.readFileSync(PID_FILE, 'utf8').trim();
  const pid = Number(raw);
  return Number.isFinite(pid) && pid > 0 ? pid : null;
}

export function removePid(): void {
  fs.rmSync(PID_FILE, { force: true });
}

export function isRunning(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export function detachChild(args: string[], env?: Record<string, string>): number | null {
  ensureStateDir();
  const child = spawn(process.execPath, args, {
    detached: true,
    stdio: 'ignore',
    env: { ...process.env, ...env },
  });
  child.unref();
  return child.pid ?? null;
}
