import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

import { assertWritable } from './policy.js';

const execFileAsync = promisify(execFile);

type ToolResult = {
  content: string;
  success: boolean;
  error?: string;
  state?: unknown;
};

/**
 * Build a child-process env that guarantees /usr/local/bin and the shared
 * venv (if present) are on PATH.  System users created by `useradd --system`
 * (e.g. sandbox-user) inherit a bare PATH that misses /usr/local/bin where
 * python3.12, node, officecli and uv live.
 */
function buildExecEnv(): NodeJS.ProcessEnv {
  const extra = ['/usr/local/bin', '/usr/bin', '/bin'];
  const current = process.env['PATH'] || '';
  const parts = current.split(path.delimiter).filter(Boolean);
  const merged = [...new Set([...extra, ...parts])].join(path.delimiter);

  const env: NodeJS.ProcessEnv = { ...process.env, PATH: merged };

  // Activate the shared venv so `python3` / `pip` resolve to 3.12 + packages.
  const venvDir = '/opt/lca/venv';
  if (!env['VIRTUAL_ENV']) {
    env['VIRTUAL_ENV'] = venvDir;
    env['PATH'] = `${venvDir}/bin:${env['PATH']}`;
  }

  return env;
}

function parseArgs(raw: string | Record<string, unknown>): Record<string, unknown> {
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return {};
    }
  }
  return raw;
}

function resolvePath(root: string, target: string): string {
  const abs = path.isAbsolute(target) ? target : path.join(root, target);
  return path.normalize(abs);
}

async function* walkDir(dir: string): AsyncGenerator<string> {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walkDir(full);
    } else {
      yield full;
    }
  }
}

function matchesGlob(filename: string, pattern: string): boolean {
  const regex = pattern
    .replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replace(/\*\*/g, '{{GLOBSTAR}}')
    .replace(/\*/g, '[^/]*')
    .replace(/\?/g, '[^/]')
    .replace(/\{\{GLOBSTAR\}\}/g, '.*');
  return new RegExp(`^${regex}$`).test(filename);
}

export async function executeToolCall(
  apiName: string,
  rawArgs: string | Record<string, unknown>,
  workspace: string,
): Promise<ToolResult> {
  const args = parseArgs(rawArgs);
  try {
    switch (apiName) {
      case 'listFiles': {
        const dir = resolvePath(workspace, String(args.directoryPath || args.directory_path || workspace));
        const entries = await fs.readdir(dir, { withFileTypes: true });
        const files = entries.map((e) => ({ name: e.name, isDirectory: e.isDirectory() }));
        return { success: true, content: JSON.stringify(files), state: { files } };
      }
      case 'readFile': {
        const file = resolvePath(workspace, String(args.path || ''));
        const text = await fs.readFile(file, 'utf8');
        return { success: true, content: text };
      }
      case 'writeFile': {
        const file = resolvePath(workspace, String(args.path || ''));
        assertWritable(file, workspace);
        await fs.mkdir(path.dirname(file), { recursive: Boolean(args.createDirectories ?? args.create_directories ?? true) });
        await fs.writeFile(file, String(args.content ?? ''), 'utf8');
        return { success: true, content: `wrote ${file}` };
      }
      case 'writeFiles': {
        const files = (args.files || {}) as Record<string, { b64?: string; url?: string }>;
        const base = String(args.base_dir || workspace);
        for (const [name, source] of Object.entries(files)) {
          const dest = resolvePath(base, name);
          assertWritable(dest, workspace);
          await fs.mkdir(path.dirname(dest), { recursive: true });
          if (source.b64) await fs.writeFile(dest, Buffer.from(source.b64, 'base64'));
        }
        return { success: true, content: `wrote ${Object.keys(files).length} files` };
      }
      case 'runCommand': {
        const command = String(args.command || '');
        const { stdout, stderr } = await execFileAsync('/bin/sh', ['-c', command], {
          cwd: workspace,
          env: buildExecEnv(),
          timeout: Number(args.timeout || 60) * 1000,
        });
        return { success: true, content: stdout, state: { stdout, stderr, command } };
      }
      case 'editFile': {
        const file = resolvePath(workspace, String(args.path || ''));
        assertWritable(file, workspace);
        const text = await fs.readFile(file, 'utf8');
        const oldStr = String(args.old_str || args.oldString || '');
        const newStr = String(args.new_str || args.newString || '');
        if (!oldStr) return { success: false, content: '', error: 'editFile requires old_str' };
        const idx = text.indexOf(oldStr);
        if (idx === -1) return { success: false, content: '', error: 'old_str not found in file' };
        const updated = text.slice(0, idx) + newStr + text.slice(idx + oldStr.length);
        await fs.writeFile(file, updated, 'utf8');
        return { success: true, content: `edited ${file}` };
      }
      case 'searchFiles': {
        const dir = resolvePath(workspace, String(args.directoryPath || args.directory_path || workspace));
        const pattern = String(args.pattern || '*');
        const matches: string[] = [];
        for await (const f of walkDir(dir)) {
          const rel = path.relative(dir, f);
          if (matchesGlob(path.basename(rel), pattern)) {
            matches.push(rel);
          }
        }
        return { success: true, content: JSON.stringify(matches) };
      }
      case 'moveFiles': {
        const src = resolvePath(workspace, String(args.source || args.src || ''));
        const dest = resolvePath(workspace, String(args.destination || args.dest || ''));
        assertWritable(src, workspace);
        assertWritable(dest, workspace);
        await fs.rename(src, dest);
        return { success: true, content: `moved ${src} -> ${dest}` };
      }
      case 'grepContent': {
        const dir = resolvePath(workspace, String(args.directoryPath || args.directory_path || workspace));
        const regex = new RegExp(String(args.pattern || ''), 'g');
        const results: { file: string; line: number; text: string }[] = [];
        for await (const f of walkDir(dir)) {
          try {
            const content = await fs.readFile(f, 'utf8');
            const lines = content.split('\n');
            for (let i = 0; i < lines.length; i++) {
              if (regex.test(lines[i])) {
                results.push({ file: path.relative(dir, f), line: i + 1, text: lines[i] });
              }
              regex.lastIndex = 0;
            }
          } catch {
            // skip unreadable files
          }
        }
        return { success: true, content: JSON.stringify(results.slice(0, 200)) };
      }
      case 'globFiles': {
        const dir = resolvePath(workspace, String(args.directoryPath || args.directory_path || workspace));
        const pattern = String(args.pattern || '**/*');
        const matches: string[] = [];
        for await (const f of walkDir(dir)) {
          const rel = path.relative(dir, f);
          if (matchesGlob(rel, pattern) || matchesGlob(path.basename(rel), pattern)) {
            matches.push(rel);
          }
        }
        return { success: true, content: JSON.stringify(matches.slice(0, 1000)) };
      }
      case 'getCommandOutput': {
        return { success: false, content: '', error: 'background commands are not supported in CLI mode' };
      }
      case 'killCommand': {
        return { success: false, content: '', error: 'background commands are not supported in CLI mode' };
      }
      case 'executeCode': {
        const code = String(args.code || '');
        const language = String(args.language || 'javascript');
        const env = buildExecEnv();
        if (language === 'python' || language === 'python3') {
          const { stdout } = await execFileAsync('python3', ['-c', code], {
            cwd: workspace,
            env,
            timeout: Number(args.timeout || 30) * 1000,
          });
          return { success: true, content: stdout };
        }
        const { stdout } = await execFileAsync('node', ['-e', code], {
          cwd: workspace,
          env,
          timeout: Number(args.timeout || 30) * 1000,
        });
        return { success: true, content: stdout };
      }
      case 'exportFile': {
        const file = resolvePath(workspace, String(args.path || ''));
        const buf = await fs.readFile(file);
        const b64 = buf.toString('base64');
        return { success: true, content: b64 };
      }
      default:
        return { success: false, content: '', error: `unknown apiName: ${apiName}` };
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return { success: false, content: '', error: message };
  }
}
