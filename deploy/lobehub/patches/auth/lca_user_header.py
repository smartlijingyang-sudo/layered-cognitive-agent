"""Patch: lca_user_header — inject ``x-lca-user-id`` from Better Auth session.

ADR-0252 D4：LCA 信任 Next.js 中间件注入的 ``x-lca-user-id``。在 mock /
logged-in 分支克隆请求头并重新执行 ``defaultMiddleware``，同时让
``defaultMiddleware`` 的所有 ``NextResponse.rewrite`` 显式携带
``request.headers``，确保 next.config rewrite 把该头转发到 LCA。
"""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="lca_user_header",
    description="Inject x-lca-user-id from Better Auth session into LCA-forwarded requests",
    files=("src/libs/next/proxy/define-config.ts",),
    risk="medium",
    category="auth",
    depends_on=("middleware_mock_user",),
    why="ADR-0252 D4: LCA trusts x-lca-user-id set by Next.js middleware",
    technical_detail=(
        "NextResponse.rewrite only forwards the request headers when "
        "`request: { headers }` is passed explicitly. The patch wires the "
        "cloned headers through defaultMiddleware so LCA receives the id."
    ),
    verify_file="src/libs/next/proxy/define-config.ts",
    verify_marker="LCA x-lca-user-id injection",
)


def apply(ctx: PatchContext) -> bool:
    rel = "src/libs/next/proxy/define-config.ts"
    if ctx.has_marker(rel, "LCA x-lca-user-id injection"):
        return False

    text = ctx.read(rel)

    # 0) NextRequest must be imported as a value (used with `new`).
    anchor_import = """import { type NextRequest } from 'next/server';
import { NextResponse } from 'next/server';"""
    repl_import = """import { NextRequest, NextResponse } from 'next/server';"""
    if anchor_import not in text:
        raise AssertionError("lca_user_header: NextRequest import anchor not found")
    text = text.replace(anchor_import, repl_import, 1)

    # 1) Add the LCA path guard after the isProtected log lines.
    anchor_guard = """    logBetterAuth('Route protection status: %s, %s', req.url, isProtected ? 'protected' : 'public');

    // Skip session lookup for public routes to reduce latency
    if (!isProtected) return response;
"""
    repl_guard = """    logBetterAuth('Route protection status: %s, %s', req.url, isProtected ? 'protected' : 'public');

    // LCA x-lca-user-id injection: LCA-forwarded paths get the header via
    // NextResponse.next so the next.config rewrite forwards it.
    const isLcaApiPath = (request: NextRequest) => {
      const pathname = request.nextUrl.pathname;
      return pathname.startsWith('/lca-api') || pathname.startsWith('/files') || pathname.startsWith('/runs');
    };

    // Skip session lookup for public routes to reduce latency
    if (!isProtected) return response;
"""
    if anchor_guard not in text:
        raise AssertionError("lca_user_header: guard anchor not found")
    text = text.replace(anchor_guard, repl_guard, 1)
    anchor_mock = """    const mockDevFlag = process.env.ENABLE_MOCK_DEV_USER;
    if (mockDevFlag === '1' || mockDevFlag === 'true') {
      logBetterAuth('ENABLE_MOCK_DEV_USER: skipping session gate');
      return response;
    }
"""
    repl_mock = """    const mockDevFlag = process.env.ENABLE_MOCK_DEV_USER;
    if (mockDevFlag === '1' || mockDevFlag === 'true') {
      logBetterAuth('ENABLE_MOCK_DEV_USER: skipping session gate');
      if (isLcaApiPath(req)) {
        const lcaHeaders = new Headers(req.headers);
        lcaHeaders.set('x-lca-user-id', process.env.MOCK_DEV_USER_ID || 'local-dev-user');
        return NextResponse.next({ request: { headers: lcaHeaders } });
      }
      return response;
    }
"""
    if anchor_mock not in text:
        raise AssertionError("lca_user_header: mock-branch anchor not found")
    text = text.replace(anchor_mock, repl_mock, 1)

    # 3) Logged-in branch: forward the authenticated user id via cloned headers.
    anchor_final = """      logBetterAuth('Request a free route but not login, allow visit without auth header');
    }

    return response;
  };
"""
    repl_final = """      logBetterAuth('Request a free route but not login, allow visit without auth header');
    }

    // LCA x-lca-user-id injection: forward the authenticated user id to LCA APIs.
    if (isLcaApiPath(req)) {
      const lcaHeaders = new Headers(req.headers);
      lcaHeaders.set('x-lca-user-id', session.user.id);
      return NextResponse.next({ request: { headers: lcaHeaders } });
    }

    return response;
  };
"""
    if anchor_final not in text:
        raise AssertionError("lca_user_header: final-return anchor not found")
    text = text.replace(anchor_final, repl_final, 1)

    ctx.write(rel, text)
    return True