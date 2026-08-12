"""Patch: middleware_mock_user — Skip Better Auth session gate for dev."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="middleware_mock_user",
    description="Skip Better Auth session gate for dev",
    files=("src/libs/next/proxy/define-config.ts",),
    risk="medium",
    category="auth",
    depends_on=(),
    why="Next.js middleware blocks unauthenticated requests; dev mode must bypass",
    technical_detail="Early-return from middleware when ENABLE_MOCK_DEV_USER flag is set.",
    verify_file="src/libs/next/proxy/define-config.ts",
    verify_marker="ENABLE_MOCK_DEV_USER: skipping session gate",
)


def apply(ctx: PatchContext) -> bool:
    """Return True if applied, False if already applied (skipped)."""
    rel = "src/libs/next/proxy/define-config.ts"
    if ctx.has_marker(rel, "ENABLE_MOCK_DEV_USER: skipping session gate"):
        return False
    anchor = """    // Skip session lookup for public routes to reduce latency
    if (!isProtected) return response;

    // Get full session with user data (Next.js 15.2.0+ feature)"""
    insert = """    // Skip session lookup for public routes to reduce latency
    if (!isProtected) return response;

    // LCA local stack: skip Better Auth session gate (LocalDevAuth + API mock user).
    const mockDevFlag = process.env.ENABLE_MOCK_DEV_USER;
    if (mockDevFlag === '1' || mockDevFlag === 'true') {
      logBetterAuth('ENABLE_MOCK_DEV_USER: skipping session gate');
      return response;
    }

    // Get full session with user data (Next.js 15.2.0+ feature)"""
    text = ctx.replace_once(rel, anchor, insert, label="middleware_mock_user")
    ctx.write(rel, text)
    return True
