"""Patch: lan_dev — Use VITE_DEV_HOST for Vite dev asset URLs."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="lan_dev",
    description="Use VITE_DEV_HOST for Vite dev asset URLs",
    files=("src/libs/spaHtml/index.ts",),
    risk="low",
    category="devux",
    depends_on=(),
    why="Developers need LAN access from mobile devices; hardcoded localhost prevents this",
    technical_detail="Replace hardcoded 'localhost' with process.env.VITE_DEV_HOST in resolveViteDevOrigin.",
    verify_file="src/libs/spaHtml/index.ts",
    verify_marker="VITE_DEV_HOST",
)


def apply(ctx: PatchContext) -> bool:
    """Return True if applied, False if already applied (skipped)."""
    rel = "src/libs/spaHtml/index.ts"
    text = ctx.read(rel)
    if "VITE_DEV_HOST" in text:
        return False
    candidates = [
        # v2.2.13: resolveViteDevOrigin with VITE_DEV_PORT
        (
            "export const resolveViteDevOrigin = () =>\n"
            "  `http://localhost:${Number(process.env.VITE_DEV_PORT) || 9876}`;",
            "export const resolveViteDevOrigin = () => {\n"
            "  const host = process.env.VITE_DEV_HOST || 'localhost';\n"
            "  const port = Number(process.env.VITE_DEV_PORT) || 9876;\n"
            "  return `http://${host}:${port}`;\n"
            "};",
        ),
        # Older: resolveCiteDevOrigin
        (
            "export const resolveCiteDevOrigin = () =>\n"
            "  `http://localhost:${Number(process.env.VITE_DEV_PORT) || 9876}`;",
            "export const resolveCiteDevOrigin = () => {\n"
            "  const host = process.env.VITE_DEV_HOST || 'localhost';\n"
            "  const port = Number(process.env.VITE_DEV_PORT) || 9876;\n"
            "  return `http://${host}:${port}`;\n"
            "};",
        ),
        (
            "export const resolveCiteDevOrigin = () =>\n"
            "  `http://localhost:${Number(process.env.CITE_DEV_PORT) || 9876}`;",
            "export const resolveCiteDevOrigin = () => {\n"
            "  const host = process.env.VITE_DEV_HOST || 'localhost';\n"
            "  const port = Number(process.env.CITE_DEV_PORT) || 9876;\n"
            "  return `http://${host}:${port}`;\n"
            "};",
        ),
    ]
    for old, new in candidates:
        if old in text:
            ctx.write(rel, text.replace(old, new, 1))
            return True
    raise SystemExit("[lan_dev] resolveViteDevOrigin/resolveCiteDevOrigin anchor not found")
