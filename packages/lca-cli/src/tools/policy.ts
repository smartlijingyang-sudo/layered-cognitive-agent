import path from 'node:path';

/** Enforce SandboxPolicy writable_roots on the CLI side. */
export function assertWritable(target: string, writableRoot: string): void {
  const resolved = path.resolve(target);
  const root = path.resolve(writableRoot);
  if (resolved !== root && !resolved.startsWith(root + path.sep)) {
    throw new Error(`path ${resolved} is outside writable root ${root}`);
  }
  const denied = [path.join(root, '.ssh'), path.join(root, '.lca')];
  for (const block of denied) {
    if (resolved === block || resolved.startsWith(block + path.sep)) {
      throw new Error(`path ${resolved} is denied`);
    }
  }
}
