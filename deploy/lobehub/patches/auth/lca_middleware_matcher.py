"""Patch: lca_middleware_matcher — run middleware on LCA-forwarded paths.

ADR-0252 D4：``src/proxy.ts`` 的 matcher 缺 ``/lca-api``，中间件不会在
LCA 转发请求上运行，导致 ``x-lca-user-id`` 无法注入。补丁把 ``/lca-api``、
``/files``、``/runs`` 加入 matcher。
"""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="lca_middleware_matcher",
    description="Add /lca-api, /files, /runs to the Next.js middleware matcher",
    files=("src/proxy.ts",),
    risk="low",
    category="auth",
    depends_on=(),
    why="ADR-0252 D4: middleware must run on LCA-forwarded paths to inject x-lca-user-id",
    technical_detail=(
        "Appends LCA path globs to the matcher array in src/proxy.ts so "
        "betterAuthMiddleware runs and NextResponse.next({ request: { headers } }) "
        "forwards the user id through next.config rewrites."
    ),
    verify_file="src/proxy.ts",
    verify_marker="LCA middleware matcher",
)


def apply(ctx: PatchContext) -> bool:
    rel = "src/proxy.ts"
    if ctx.has_marker(rel, "LCA middleware matcher"):
        return False

    text = ctx.read(rel)

    anchor = """    '/market-auth-callback(.*)',
  ],
};"""
    repl = """    '/market-auth-callback(.*)',

    // LCA middleware matcher: /lca-api, /files, /runs are forwarded to the
    // LCA gateway via next.config rewrites; run the middleware so the session
    // user id can be injected as x-lca-user-id (ADR-0252 D4).
    '/lca-api',
    '/lca-api(.*)',
    '/files',
    '/files(.*)',
    '/runs',
    '/runs(.*)',
  ],
};"""
    if anchor not in text:
        raise AssertionError("lca_middleware_matcher: matcher anchor not found")
    text = text.replace(anchor, repl, 1)

    ctx.write(rel, text)
    return True