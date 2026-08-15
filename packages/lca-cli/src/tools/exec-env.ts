import path from 'node:path';

/**
 * Child-process env for the host machine face.
 *
 * ``useradd --system`` (sandbox-user) inherits a bare PATH. The shared venv
 * and /usr/local/bin must be first so ``python3`` is the provisioned one.
 */
export function buildExecEnv(): NodeJS.ProcessEnv {
  const extra = ['/usr/local/bin', '/usr/bin', '/bin'];
  const current = process.env['PATH'] || '';
  const parts = current.split(path.delimiter).filter(Boolean);
  const merged = [...new Set([...extra, ...parts])].join(path.delimiter);
  const env: NodeJS.ProcessEnv = { ...process.env, PATH: merged };

  const venvDir = process.env['VIRTUAL_ENV'] || '/opt/lca/venv';
  if (!env['VIRTUAL_ENV']) {
    env['VIRTUAL_ENV'] = venvDir;
  }
  env['PATH'] = `${venvDir}/bin:${env['PATH']}`;
  return env;
}
