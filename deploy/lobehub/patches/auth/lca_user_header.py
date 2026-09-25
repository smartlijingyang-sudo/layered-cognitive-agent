"""Patch: lca_user_header — inject ``x-lca-user-id`` from Better Auth session.

ADR-0252 D4：LCA 信任 Next.js 中间件注入的 ``x-lca-user-id``（mock 分支注入
``MOCK_DEV_USER_ID``）。补丁在会话解析后把用户 id 加进转发请求的头里。
"""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="lca_user_header",
    description="Inject x-lca-user-id from Better Auth session into rewritten requests",
    files=("src/libs/next/proxy/define-config.ts",),
    risk="medium",
    category="auth",
    depends_on=("middleware_mock_user",),
    why="ADR-0252 D4: LCA trusts x-lca-user-id set by Next.js middleware",
    technical_detail=(
        "In the mock branch forward MOCK_DEV_USER_ID; in the logged-in branch "
        "forward session.user.id. Re-runs defaultMiddleware with the cloned "
        "headers so the next.config rewrite forwards the header to LCA."
    ),
    verify_file="src/libs/next/proxy/define-config.ts",
    verify_marker="LCA x-lca-user-id injection",
)


def apply(ctx: PatchContext) -> bool:
    rel = "src/libs/next/proxy/define-config.ts"
    if ctx.has_marker(rel, "LCA x-lca-user-id injection"):
        return False

    text = ctx.read(rel)

    # 1) Mock branch: forward the mock dev user id.
    anchor_mock = """    const mockDevFlag = process.env.ENABLE_MOCK_DEV_USER;
    if (mockDevFlag === '1' || mockDevFlag === 'true') {
      logBetterAuth('ENABLE_MOCK_DEV_USER: skipping session gate');
      return response;
    }
"""
    repl_mock = """    const mockDevFlag = process.env.ENABLE_MOCK_DEV_USER;
    if (mockDevFlag === '1' || mockDevFlag === 'true') {
      logBetterAuth('ENABLE_MOCK_DEV_USER: skipping session gate');
      // LCA x-lca-user-id injection: forward the mock user id to LCA APIs.
      const lcaHeaders = new Headers(req.headers);
      lcaHeaders.set('x-lca-user-id', process.env.MOCK_DEV_USER_ID || 'local-dev-user');
      return defaultMiddleware(new NextRequest(req.url, { headers: lcaHeaders }));
    }
"""
    if anchor_mock not in text:
        raise AssertionError("lca_user_header: mock-branch anchor not found")
    text = text.replace(anchor_mock, repl_mock, 1)

    # 2) Logged-in branch: forward the authenticated user id.
    anchor_final = """      logBetterAuth('Request a free route but not login, allow visit without auth header');
    }

    return response;
  };
"""
    repl_final = """      logBetterAuth('Request a free route but not login, allow visit without auth header');
    }

    // LCA x-lca-user-id injection: forward the authenticated user id to LCA APIs.
    const lcaHeaders = new Headers(req.headers);
    lcaHeaders.set('x-lca-user-id', session.user.id);
    return defaultMiddleware(new NextRequest(req.url, { headers: lcaHeaders }));
  };
"""
    if anchor_final not in text:
        raise AssertionError("lca_user_header: final-return anchor not found")
    text = text.replace(anchor_final, repl_final, 1)

    ctx.write(rel, text)
    return True