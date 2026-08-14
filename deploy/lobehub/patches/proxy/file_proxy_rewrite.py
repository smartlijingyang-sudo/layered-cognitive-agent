"""Patch: file_proxy_rewrite — Proxy /files/* and /lca-api/* to LCA gateway."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="file_proxy_rewrite",
    description="Proxy /files/* and /lca-api/* to LCA gateway",
    files=("next.config.ts", "vite.config.ts"),
    risk="low",
    category="proxy",
    depends_on=(),
    why="LCA tool artifacts and Run live are served by the gateway, not LobeHub",
    technical_detail="Next rewrites and Vite proxy: /files, /lca-api/runs → gateway.",
    verify_file="next.config.ts",
    verify_marker="LCA: file proxy",
)

_VITE_MARKER = "LCA: file proxy"


def apply(ctx: PatchContext) -> bool:
    changed = _patch_next(ctx)
    changed = _patch_vite(ctx) or changed
    return _ensure_vite_ws(ctx) or changed


def _patch_next(ctx: PatchContext) -> bool:
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
        source: '/lca-api/runs',
        destination: `${base.replace(/\\/$/, '')}/runs`,
      },
      {
        source: '/lca-api/runs/:path*',
        destination: `${base.replace(/\\/$/, '')}/runs/:path*`,
      },
      {
        source: '/runs/:path*',
        destination: `${base.replace(/\\/$/, '')}/runs/:path*`,
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


def _patch_vite(ctx: PatchContext) -> bool:
    rel = "vite.config.ts"
    text = ctx.read(rel)
    if _VITE_MARKER in text:
        return False
    needle = "      '/webapi': `http://localhost:${process.env.PORT || 3010}`,\n    },"
    insert = """      '/webapi': `http://localhost:${process.env.PORT || 3010}`,
      // LCA: file proxy
      '/files': process.env.LCA_GATEWAY_PUBLIC_URL || 'http://127.0.0.1:8765',
      '/lca-api': {
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\\/lca-api/, ''),
        target: process.env.LCA_GATEWAY_PUBLIC_URL || 'http://127.0.0.1:8765',
        ws: true,
      },
    },"""
    if needle not in text:
        return False
    ctx.write(rel, text.replace(needle, insert, 1))
    return True


def _ensure_vite_ws(ctx: PatchContext) -> bool:
    rel = "vite.config.ts"
    text = ctx.read(rel)
    if "ws: true" in text and "/lca-api" in text:
        return False
    applied = """      '/lca-api': {
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\\/lca-api/, ''),
        target: process.env.LCA_GATEWAY_PUBLIC_URL || 'http://127.0.0.1:8765',
      },"""
    new = """      '/lca-api': {
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\\/lca-api/, ''),
        target: process.env.LCA_GATEWAY_PUBLIC_URL || 'http://127.0.0.1:8765',
        ws: true,
      },"""
    if applied not in text:
        return False
    ctx.write(rel, text.replace(applied, new, 1))
    return True
