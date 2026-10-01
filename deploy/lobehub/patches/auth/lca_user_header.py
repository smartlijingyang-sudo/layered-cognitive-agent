"""Patch: lca_user_header — inject ``x-lca-user-id`` and auth token from Better Auth session.

ADR-0252 D4：LCA 信任 Next.js 中间件注入的 ``x-lca-user-id`` 与后端认证 Token。
在 mock / logged-in 分支克隆请求头，注入用户 ID 与 ``Authorization: Bearer <LCA_TOKEN>``，
并经由 ``NextResponse.next({ request: { headers: lcaHeaders } })`` 转发至 LCA 内核。
"""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="lca_user_header",
    description="Inject x-lca-user-id and auth token from Better Auth session into LCA-forwarded requests",
    files=("src/libs/next/proxy/define-config.ts",),
    risk="medium",
    category="auth",
    depends_on=("middleware_mock_user",),
    why="ADR-0252 D4: LCA trusts x-lca-user-id and gateway auth token set by Next.js middleware",
    technical_detail=(
        "NextResponse.rewrite only forwards the request headers when "
        "`request: { headers }` is passed explicitly. The patch wires the "
        "cloned headers through defaultMiddleware so LCA receives the user id "
        "and authorization token, and bypasses sign-in redirect for LCA API paths."
    ),
    verify_file="src/libs/next/proxy/define-config.ts",
    verify_marker="LCA x-lca-user-id and auth token injection (bypass signin)",
)


def apply(ctx: PatchContext) -> bool:
    rel = "src/libs/next/proxy/define-config.ts"
    if ctx.has_marker(rel, meta.verify_marker):
        return False

    text = ctx.read(rel)

    unauth_bypass = """      // LCA API unauthenticated bypass: forward dev/request credentials without redirecting to sign-in page.
      if (isLcaApiPath(req)) {
        const lcaHeaders = new Headers(req.headers);
        const devUserId = lcaHeaders.get('x-lca-user-id') || process.env.MOCK_DEV_USER_ID || 'local-dev-user';
        lcaHeaders.set('x-lca-user-id', devUserId);
        const lcaToken = process.env.LCA_TOKEN || process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
        if (!lcaHeaders.has('authorization')) {
          lcaHeaders.set('authorization', `Bearer ${lcaToken}`);
        }
        lcaHeaders.set('x-lca-token', lcaToken);
        return NextResponse.next({ request: { headers: lcaHeaders } });
      }"""

    new_mock = """      if (isLcaApiPath(req)) {
        const lcaHeaders = new Headers(req.headers);
        const devUserId = lcaHeaders.get('x-lca-user-id') || process.env.MOCK_DEV_USER_ID || 'local-dev-user';
        lcaHeaders.set('x-lca-user-id', devUserId);
        const lcaToken = process.env.LCA_TOKEN || process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
        if (!lcaHeaders.has('authorization')) {
          lcaHeaders.set('authorization', `Bearer ${lcaToken}`);
        }
        lcaHeaders.set('x-lca-token', lcaToken);
        return NextResponse.next({ request: { headers: lcaHeaders } });
      }"""

    new_final = """    // LCA x-lca-user-id and auth token injection (bypass signin): forward authenticated user and gateway token to LCA APIs.
    if (isLcaApiPath(req)) {
      const lcaHeaders = new Headers(req.headers);
      lcaHeaders.set('x-lca-user-id', session.user.id);
      const lcaToken = process.env.LCA_TOKEN || process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
      if (!lcaHeaders.has('authorization')) {
        lcaHeaders.set('authorization', `Bearer ${lcaToken}`);
      }
      lcaHeaders.set('x-lca-token', lcaToken);
      return NextResponse.next({ request: { headers: lcaHeaders } });
    }"""

    # Check if upgrading an older version of the patch
    old_final_v1 = """    // LCA x-lca-user-id injection: forward the authenticated user id to LCA APIs.
    if (isLcaApiPath(req)) {
      const lcaHeaders = new Headers(req.headers);
      lcaHeaders.set('x-lca-user-id', session.user.id);
      return NextResponse.next({ request: { headers: lcaHeaders } });
    }"""

    old_final_v2 = """    // LCA x-lca-user-id and auth token injection: forward authenticated user and gateway token to LCA APIs.
    if (isLcaApiPath(req)) {
      const lcaHeaders = new Headers(req.headers);
      lcaHeaders.set('x-lca-user-id', session.user.id);
      const lcaToken = process.env.LCA_TOKEN || process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
      lcaHeaders.set('authorization', `Bearer ${lcaToken}`);
      return NextResponse.next({ request: { headers: lcaHeaders } });
    }"""

    old_mock_v1 = """      if (isLcaApiPath(req)) {
        const lcaHeaders = new Headers(req.headers);
        lcaHeaders.set('x-lca-user-id', process.env.MOCK_DEV_USER_ID || 'local-dev-user');
        return NextResponse.next({ request: { headers: lcaHeaders } });
      }"""

    old_mock_v2 = """      if (isLcaApiPath(req)) {
        const lcaHeaders = new Headers(req.headers);
        lcaHeaders.set('x-lca-user-id', process.env.MOCK_DEV_USER_ID || 'local-dev-user');
        const lcaToken = process.env.LCA_TOKEN || process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
        lcaHeaders.set('authorization', `Bearer ${lcaToken}`);
        return NextResponse.next({ request: { headers: lcaHeaders } });
      }"""

    # 1) Expand backendApiEndpoints if present
    anchor_endpoints = "  const backendApiEndpoints = ['/api', '/trpc', '/webapi', '/oidc', '/oauth/connector'];"
    repl_endpoints = "  const backendApiEndpoints = ['/api', '/trpc', '/webapi', '/oidc', '/oauth/connector', '/lca-api', '/files', '/runs'];"
    if anchor_endpoints in text:
        text = text.replace(anchor_endpoints, repl_endpoints, 1)

    # 2) Upgrades for already patched files:
    is_upgrade = (old_final_v1 in text) or (old_final_v2 in text)
    if is_upgrade:
        if old_final_v1 in text:
            text = text.replace(old_final_v1, new_final, 1)
        elif old_final_v2 in text:
            text = text.replace(old_final_v2, new_final, 1)

        if old_mock_v1 in text:
            text = text.replace(old_mock_v1, new_mock, 1)
        elif old_mock_v2 in text:
            text = text.replace(old_mock_v2, new_mock, 1)

        anchor_unauth = "    if (!isLoggedIn) {\n"
        if "LCA API unauthenticated bypass" not in text and anchor_unauth in text:
            text = text.replace(anchor_unauth, f"{anchor_unauth}{unauth_bypass}\n\n", 1)

        ctx.write(rel, text)
        return True

    # 3) Fresh application on clean upstream file:
    anchor_import = """import { type NextRequest } from 'next/server';
import { NextResponse } from 'next/server';"""
    repl_import = """import { NextRequest, NextResponse } from 'next/server';"""
    if anchor_import not in text:
        raise AssertionError("lca_user_header: NextRequest import anchor not found")
    text = text.replace(anchor_import, repl_import, 1)

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
    repl_mock = f"""    const mockDevFlag = process.env.ENABLE_MOCK_DEV_USER;
    if (mockDevFlag === '1' || mockDevFlag === 'true') {{
      logBetterAuth('ENABLE_MOCK_DEV_USER: skipping session gate');
{new_mock}
      return response;
    }}
"""
    if anchor_mock not in text:
        raise AssertionError("lca_user_header: mock-branch anchor not found")
    text = text.replace(anchor_mock, repl_mock, 1)

    anchor_unauth = "    if (!isLoggedIn) {\n"
    if anchor_unauth not in text:
        raise AssertionError("lca_user_header: unauth-branch anchor not found")
    text = text.replace(anchor_unauth, f"{anchor_unauth}{unauth_bypass}\n\n", 1)

    anchor_final = """      logBetterAuth('Request a free route but not login, allow visit without auth header');
    }

    return response;
  };
"""
    repl_final = f"""      logBetterAuth('Request a free route but not login, allow visit without auth header');
    }}

{new_final}

    return response;
  }};
"""
    if anchor_final not in text:
        raise AssertionError("lca_user_header: final-return anchor not found")
    text = text.replace(anchor_final, repl_final, 1)

    ctx.write(rel, text)
    return True
