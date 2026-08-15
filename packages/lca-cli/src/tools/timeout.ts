/** Align with ``lca.layer0_infra.tools.lca_computer.executor._resolve_timeout_s``. */

const DEFAULT_TIMEOUT_S = 60;
const SECONDS_CEILING = 300;

export function resolveTimeoutMs(args: Record<string, unknown>, fallbackS = DEFAULT_TIMEOUT_S): number {
  return resolveTimeoutS(args, fallbackS) * 1000;
}

export function resolveTimeoutS(args: Record<string, unknown>, fallbackS = DEFAULT_TIMEOUT_S): number {
  const explicitS = args['timeout_s'];
  if (typeof explicitS === 'number' && Number.isFinite(explicitS) && explicitS > 0) {
    return Math.max(1, Math.trunc(explicitS));
  }
  const raw = args['timeout'];
  if (typeof raw === 'number' && Number.isFinite(raw) && raw > 0) {
    const value = Math.trunc(raw);
    if (value <= SECONDS_CEILING) {
      return Math.max(1, value);
    }
    return Math.max(1, Math.trunc(value / 1000));
  }
  return fallbackS;
}
