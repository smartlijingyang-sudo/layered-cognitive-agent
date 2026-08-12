"""Patch: file_proxy_rewrite — Proxy /files/* to LCA gateway for artifact downloads."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="file_proxy_rewrite",
    description="Proxy /files/* to LCA gateway for artifact downloads",
    files=("next.config.ts",),
    risk="low",
    category="proxy",
    depends_on=(),
    why="LCA tool artifacts are served by the gateway, not LobeHub's file system",
    technical_detail="Add Next.js rewrite rule: /files/* → LCA gateway /files/* endpoint.",
    verify_file="next.config.ts",
    verify_marker="LCA: file proxy",
)


def apply(ctx: PatchContext) -> bool:
    """Return True if applied, False if already applied (skipped)."""
    rel = "next.config.ts"
    text = ctx.read(rel)
    if "LCA: file proxy" in text:
        return False
    old = "const nextConfig = defineConfig({"
    new = "const _baseConfig = defineConfig({"
    if old not in text:
        return False
    text = text.replace(old, new, 1)
    old_end = "});\n\nexport default nextConfig;"
    new_end = """});

// LCA: file proxy — artifact downloads via Next.js rewrite → LCA gateway
const nextConfig = {
  ..._baseConfig,
  async rewrites() {
    const base = process.env.LCA_GATEWAY_PUBLIC_URL || 'http://127.0.0.1:8765';
    const baseRewrites = typeof _baseConfig.rewrites === 'function'
      ? await _baseConfig.rewrites()
      : [];
    return [
      ...(Array.isArray(baseRewrites) ? baseRewrites : []),
      {
        source: '/files/:path*',
        destination: `${base.replace(/\\/$/, '')}/files/:path*`,
      },
      {
        source: '/lca-api/:path*',
        destination: `${base.replace(/\\/$/, '')}/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;"""
    if old_end not in text:
        return False
    text = text.replace(old_end, new_end, 1)
    ctx.write(rel, text)
    return True
